"""Self-critique: deterministic code review.

Runs entirely offline. Three families of checks, each tied to a documented
real-world failure:

  1. Secrets scanning — hardcoded credentials are among the most common and most
     damaging patterns to slip through agent-authored code.
  2. Vulnerability patterns — AI-generated code carries a measurably higher
     vulnerability rate (eval/exec, shell injection, unsafe deserialisation,
     SQL string interpolation).
  3. Fake-completion / stub detection — functions left as TODO/`pass`/
     NotImplementedError while being reported as "implemented".

The critic returns structured findings; the reasoning engine uses CRITICAL/HIGH
findings as a hard gate before a change is accepted or committed.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path


class Severity(IntEnum):
    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.name


@dataclass
class Finding:
    severity: Severity
    rule: str
    message: str
    line: int = 0
    snippet: str = ""


@dataclass
class Critique:
    findings: list[Finding] = field(default_factory=list)
    syntax_ok: bool = True

    @property
    def max_severity(self) -> Severity:
        return max((f.severity for f in self.findings), default=Severity.INFO)

    @property
    def blocking(self) -> bool:
        """Whether this critique should block acceptance of the code."""
        return not self.syntax_ok or self.max_severity >= Severity.HIGH

    def by_severity(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: (-f.severity, f.line))

    def summary(self) -> str:
        if not self.findings and self.syntax_ok:
            return "no issues found"
        counts: dict[str, int] = {}
        for f in self.findings:
            counts[f.severity.name] = counts.get(f.severity.name, 0) + 1
        parts = [f"{n} {sev.lower()}" for sev, n in counts.items()]
        prefix = "" if self.syntax_ok else "SYNTAX ERROR; "
        return prefix + ", ".join(parts)


# --- secret patterns --------------------------------------------------------
# (rule, compiled regex, severity)
_SECRET_RULES: list[tuple[str, re.Pattern[str], Severity]] = [
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|ANPA)[0-9A-Z]{16}\b"), Severity.CRITICAL),
    ("private-key-block", re.compile(
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?(?:PRIVATE KEY|PRIVATE KEY BLOCK)-----"),
     Severity.CRITICAL),
    ("github-token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b"), Severity.CRITICAL),
    ("github-pat-finegrained", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), Severity.CRITICAL),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), Severity.CRITICAL),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b"), Severity.CRITICAL),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}\b"), Severity.CRITICAL),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), Severity.CRITICAL),
    ("stripe-key", re.compile(r"\b(?:sk|rk)_live_[0-9A-Za-z]{16,}\b"), Severity.CRITICAL),
    ("url-embedded-credential", re.compile(
        r"\b[a-z][a-z0-9+.\-]*://[^\s:@/]+:[^\s:@/]+@"), Severity.HIGH),
    ("generic-assigned-secret", re.compile(
        r"(?i)(password|passwd|secret|api[_-]?key|token|access[_-]?key|client[_-]?secret|"
        r"auth[_-]?token|bearer)\s*[:=]\s*"
        r"['\"][^'\"\n]{6,}['\"]"), Severity.HIGH),
]

# Tokens that mark a value as an obvious placeholder rather than a real secret.
# IMPORTANT: this is matched against the MATCHED SECRET TEXT only (not the whole
# line), so adding a benign comment elsewhere on the line cannot suppress a real
# finding (a previously exploitable bypass).
_PLACEHOLDER = re.compile(
    r"(?i)(your[_-]?|example|placeholder|changeme|x{4,}|<[a-z0-9_\- ]{1,40}>|"
    r"\bdummy\b|\bfake\b|\bredacted\b|\.\.\.)")

# --- dangerous code patterns (text-based, language-agnostic) ----------------
_DANGER_TEXT_RULES: list[tuple[str, re.Pattern[str], Severity, str]] = [
    ("os-system", re.compile(r"\bos\.system\s*\("), Severity.HIGH,
     "os.system executes via the shell — prefer subprocess with a list of args"),
    ("os-popen", re.compile(r"\bos\.popen[234]?\s*\("), Severity.HIGH,
     "os.popen runs via the shell — prefer subprocess with a list of args"),
    ("subprocess-getoutput", re.compile(r"\bsubprocess\.get(?:status)?output\s*\("),
     Severity.HIGH, "subprocess.getoutput runs via the shell — shell injection risk"),
    ("os-exec-spawn", re.compile(r"\bos\.(?:exec|spawn)[lv]p?e?\s*\("), Severity.MEDIUM,
     "os.exec*/os.spawn* invokes external programs — validate inputs"),
    ("yaml-unsafe", re.compile(r"\byaml\.(?:load|unsafe_load|full_load)\s*\((?![^)]*Loader=yaml\.Safe)"),
     Severity.HIGH, "unsafe yaml load can execute arbitrary objects — use safe_load"),
    ("pickle-loads", re.compile(r"\b(?:pickle|cPickle|dill|marshal)\.loads?\s*\("), Severity.HIGH,
     "deserialisation of untrusted data can execute code"),
    ("weak-hash", re.compile(r"\bhashlib\.(?:md5|sha1)\s*\("), Severity.LOW,
     "md5/sha1 are not collision-resistant — avoid for security-sensitive hashing"),
    ("tls-verify-disabled", re.compile(r"verify\s*=\s*False|_create_unverified_context"),  # god:allow vuln:tls-verify-disabled
     Severity.MEDIUM, "TLS verification disabled — exposes traffic to MITM"),
]

_STUB_COMMENT = re.compile(r"#\s*(TODO|FIXME|XXX|HACK)\b", re.IGNORECASE)

# Inline suppression, e.g.  `# god:allow shell-injection`  or  `# god:allow`.
# A blanket `# god:allow` suppresses non-secret findings on that line; secret
# findings require the rule to be named explicitly (so a stray blanket comment
# can never silently hide a credential).
_SUPPRESS_RE = re.compile(r"#\s*god:allow(?:\s+([\w:,\-]+))?")


class SelfCritic:
    """Deterministic, offline code reviewer."""

    def review(self, code: str, filename: str = "<generated>") -> Critique:
        critique = Critique()
        is_python = (filename == "<generated>"
                     or filename.lower().endswith((".py", ".pyw", ".pyi", ".pyx", ".py3")))

        if is_python:
            try:
                tree = ast.parse(code)
            except SyntaxError as exc:
                critique.syntax_ok = False
                critique.findings.append(Finding(
                    Severity.CRITICAL, "syntax-error",
                    f"Python does not parse: {exc.msg}", exc.lineno or 0))
                # Still run text-based scans (secrets) even if it won't parse.
                self._scan_text(code, critique)
                return critique
            self._scan_ast(tree, code, critique)

        self._scan_text(code, critique)
        self._apply_suppressions(code, critique)
        return critique

    def review_file(self, path: str | Path) -> Critique:
        p = Path(path)
        return self.review(p.read_text(encoding="utf-8", errors="ignore"), str(p))

    # ---- suppression -------------------------------------------------------
    def _apply_suppressions(self, code: str, critique: Critique) -> None:
        lines = code.splitlines()
        kept: list[Finding] = []
        for f in critique.findings:
            line_text = lines[f.line - 1] if 0 < f.line <= len(lines) else ""
            m = _SUPPRESS_RE.search(line_text)
            if m and self._is_suppressed(f.rule, m.group(1)):
                continue
            kept.append(f)
        critique.findings = kept

    @staticmethod
    def _is_suppressed(rule: str, spec: str | None) -> bool:
        is_secret = rule.startswith("secret:")
        if spec is None:
            # Blanket suppression never hides secrets.
            return not is_secret
        names = {s.strip() for s in spec.split(",") if s.strip()}
        return rule in names or rule.split(":")[-1] in names

    # ---- text scans --------------------------------------------------------
    def _scan_text(self, code: str, critique: Critique) -> None:
        lines = code.splitlines()
        for rule, pattern, severity in _SECRET_RULES:
            for m in pattern.finditer(code):
                line_no = code.count("\n", 0, m.start()) + 1
                line_text = lines[line_no - 1] if line_no - 1 < len(lines) else ""
                # Placeholder check is scoped to the MATCHED secret text only,
                # so a benign token elsewhere on the line cannot suppress a real
                # finding.
                if _PLACEHOLDER.search(m.group(0)):
                    continue
                critique.findings.append(Finding(
                    severity, f"secret:{rule}",
                    "Possible hardcoded secret — move to an env var / secret store.",
                    line_no, _redact(line_text, m.group(0))))

        for rule, pattern, severity, msg in _DANGER_TEXT_RULES:
            for m in pattern.finditer(code):
                line_no = code.count("\n", 0, m.start()) + 1
                line_text = lines[line_no - 1] if line_no - 1 < len(lines) else ""
                critique.findings.append(Finding(
                    severity, f"vuln:{rule}", msg, line_no, line_text.strip()[:100]))

        for i, line in enumerate(lines, start=1):
            if _STUB_COMMENT.search(line):
                critique.findings.append(Finding(
                    Severity.LOW, "stub:todo-comment",
                    "Unfinished work marker present (TODO/FIXME).", i, line.strip()[:100]))

    # ---- AST scans ---------------------------------------------------------
    def _scan_ast(self, tree: ast.AST, code: str, critique: Critique) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # eval / exec / compile as a bare builtin call, OR
                # <module>.eval / <module>.exec attribute access. NOTE: we do
                # NOT flag attribute `.compile` — re.compile() is benign and
                # ubiquitous, and flagging it produced false positives.
                if isinstance(node.func, ast.Name):
                    if node.func.id in ("eval", "exec", "compile"):
                        critique.findings.append(Finding(
                            Severity.HIGH, "vuln:dynamic-exec",
                            f"Use of {node.func.id}() — arbitrary code execution risk.",
                            node.lineno))
                elif isinstance(node.func, ast.Attribute):
                    if node.func.attr in ("eval", "exec"):
                        critique.findings.append(Finding(
                            Severity.HIGH, "vuln:dynamic-exec",
                            f"Use of {node.func.attr}() — arbitrary code execution risk.",
                            node.lineno))
                # subprocess(..., shell=True) — AST-based so a nested call
                # argument cannot defeat detection (a regex bypass).
                if self._call_name(node.func) in (
                        "run", "call", "Popen", "check_output", "check_call"):
                    for kw in node.keywords:
                        if (kw.arg == "shell" and isinstance(kw.value, ast.Constant)
                                and kw.value.value is True):
                            critique.findings.append(Finding(
                                Severity.HIGH, "vuln:shell-injection",
                                "subprocess called with shell=True — shell injection risk.",
                                getattr(kw.value, "lineno", node.lineno)))
            # bare except
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                critique.findings.append(Finding(
                    Severity.LOW, "smell:bare-except",
                    "Bare 'except:' swallows all errors, including KeyboardInterrupt.",
                    node.lineno))
            # SQL string interpolation passed to execute()
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("execute", "executemany", "executescript")
                    and node.args):
                arg = node.args[0]
                if isinstance(arg, (ast.JoinedStr, ast.BinOp)) or (
                        isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute)
                        and arg.func.attr == "format"):
                    critique.findings.append(Finding(
                        Severity.HIGH, "vuln:sql-injection",
                        "SQL built via string formatting — use parameterised queries.",
                        node.lineno))

        # stub / fake-completion detection on function bodies
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._check_stub(node, critique)

    @staticmethod
    def _call_name(func: ast.AST) -> str | None:
        """Return the called name for ast.Name (foo) or ast.Attribute (a.b.foo)."""
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
        return None

    def _check_stub(self, fn: ast.FunctionDef | ast.AsyncFunctionDef,
                    critique: Critique) -> None:
        # Abstract methods, overloads, and protocol members are intentional
        # stubs — do not flag them as fake completion.
        for dec in fn.decorator_list:
            dec_name = self._call_name(dec) or (dec.id if isinstance(dec, ast.Name) else None)
            if dec_name in ("abstractmethod", "abstractproperty", "overload"):
                return
        body = [n for n in fn.body if not (isinstance(n, ast.Expr)
                                           and isinstance(n.value, ast.Constant)
                                           and isinstance(n.value.value, str))]
        # body is now without the docstring
        only_pass = len(body) == 1 and isinstance(body[0], ast.Pass)
        only_ellipsis = (len(body) == 1 and isinstance(body[0], ast.Expr)
                         and isinstance(body[0].value, ast.Constant)
                         and body[0].value.value is Ellipsis)
        raises_ni = (len(body) == 1 and isinstance(body[0], ast.Raise)
                     and self._is_not_implemented(body[0]))
        if only_pass or only_ellipsis or raises_ni:
            critique.findings.append(Finding(
                Severity.MEDIUM, "stub:empty-function",
                f"Function '{fn.name}' is an unimplemented stub — verify it is "
                f"genuinely complete before claiming done.", fn.lineno))

    @staticmethod
    def _is_not_implemented(raise_node: ast.Raise) -> bool:
        exc = raise_node.exc
        if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
            return exc.func.id == "NotImplementedError"
        if isinstance(exc, ast.Name):
            return exc.id == "NotImplementedError"
        return False


def _redact(line: str, secret: str | None = None) -> str:
    """Redact the likely secret value so the audit/output never echoes it.

    Redacts (a) the exact matched secret span when provided, (b) any quoted
    value, and (c) long token-like runs — covering unquoted secrets that the
    quote-only redaction used to leak.
    """
    text = line
    if secret:
        text = text.replace(secret, "***REDACTED***")
    text = re.sub(r"(['\"])[^'\"]{4,}(['\"])", r"\1***REDACTED***\2", text)
    text = re.sub(r"\b[A-Za-z0-9_\-]{16,}\b", "***REDACTED***", text)
    return text.strip()[:100]
