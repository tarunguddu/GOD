"""Proactive engine — the agent that anticipates instead of only reacting.

Runs a fully-deterministic, offline project-health analysis and emits a
prioritized list of suggestions the user did not have to ask for:

  - security/quality: critique findings across the source tree
  - complexity: high-complexity hotspots from the code graph
  - testing: source modules with no corresponding test file
  - maintainability: oversized files, dense TODO/FIXME markers

It also offers a *bounded* watch mode: a poll-based watcher that re-analyses
changed files. It is deliberately time/poll-boxed (never an open-ended
autonomous run) in line with the project's safety stance.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .loop import _is_test_path
from .reasoning.critic import Severity


_LARGE_FILE_LINES = 400
_HOTSPOT_COMPLEXITY = 12
_TODO_DENSITY = 5  # markers per file before it's flagged


@dataclass
class Suggestion:
    category: str            # security | complexity | testing | maintainability
    severity: Severity
    message: str
    location: str = ""
    action: str = ""

    def render(self) -> str:
        loc = f" ({self.location})" if self.location else ""
        act = f"  -> {self.action}" if self.action else ""
        return f"[{self.severity.name}] {self.category}: {self.message}{loc}{act}"


@dataclass
class HealthReport:
    suggestions: list[Suggestion] = field(default_factory=list)
    scanned_files: int = 0

    @property
    def score(self) -> int:
        """A 0-100 health score; higher is better."""
        penalty = 0
        weights = {Severity.CRITICAL: 25, Severity.HIGH: 12,
                   Severity.MEDIUM: 5, Severity.LOW: 2, Severity.INFO: 1}
        for s in self.suggestions:
            penalty += weights.get(s.severity, 1)
        return max(0, 100 - penalty)

    def by_severity(self) -> list[Suggestion]:
        return sorted(self.suggestions, key=lambda s: (-int(s.severity), s.category))

    def by_category(self) -> dict[str, list[Suggestion]]:
        out: dict[str, list[Suggestion]] = {}
        for s in self.suggestions:
            out.setdefault(s.category, []).append(s)
        return out

    def render(self, top: int | None = None) -> str:
        lines = [f"Project health score: {self.score}/100 "
                 f"({len(self.suggestions)} suggestions over {self.scanned_files} files)"]
        items = self.by_severity()
        if top:
            items = items[:top]
        for s in items:
            lines.append("  " + s.render())
        if not items:
            lines.append("  no issues found — looking healthy")
        return "\n".join(lines)


@dataclass
class WatchEvent:
    changed: list[str]
    report: HealthReport


class ProactiveEngine:
    def __init__(self, agent) -> None:  # agent: GodAgent (avoid import cycle)
        self.agent = agent

    # ---- one-shot analysis -------------------------------------------------
    def analyze(self, paths: list[str] | None = None) -> HealthReport:
        report = HealthReport()
        # Distinguish "scan everything" (None) from "scan exactly these" (a
        # possibly-empty list) — an empty list must NOT fall back to a full scan.
        files = self._source_files() if paths is None else paths
        report.scanned_files = len(files)

        self._scan_quality(files, report)
        self._scan_complexity(files, report)
        self._scan_testing(files, report)
        self._scan_maintainability(files, report)
        return report

    def _source_files(self) -> list[str]:
        root = self.agent.boundary.root
        out: list[str] = []
        for p in root.rglob("*.py"):
            rel = str(p.relative_to(root))
            if _is_test_path(rel):
                continue
            if any(part in {".god", ".git", "__pycache__", ".venv", "venv",
                            "build", "dist"} for part in p.parts):
                continue
            out.append(rel)
        return out

    # ---- scanners ----------------------------------------------------------
    def _scan_quality(self, files: list[str], report: HealthReport) -> None:
        for rel in files:
            try:
                critique = self.agent.reasoning.critic.review_file(
                    self.agent.boundary.check(rel))
            except Exception:
                continue
            for f in critique.findings:
                if f.severity < Severity.MEDIUM:
                    continue
                category = "security" if f.rule.startswith(("secret:", "vuln:")) else "maintainability"
                report.suggestions.append(Suggestion(
                    category=category, severity=f.severity,
                    message=f.message, location=f"{rel}:{f.line}",
                    action=f"resolve {f.rule}",
                ))

    def _scan_complexity(self, files: list[str], report: HealthReport) -> None:
        fileset = set(files)
        try:
            self.agent.perceive()
            hotspots = self.agent.context.graph.hotspots(top=50)
        except Exception:
            return
        for node in hotspots:
            if node.file not in fileset:
                continue
            if node.complexity < _HOTSPOT_COMPLEXITY:
                continue
            report.suggestions.append(Suggestion(
                category="complexity", severity=Severity.MEDIUM,
                message=f"high complexity ({node.complexity}) in {node.qualified_name}",
                location=f"{node.file}:{node.line}",
                action="consider decomposing and adding focused tests",
            ))

    def _scan_testing(self, files: list[str], report: HealthReport) -> None:
        root = self.agent.boundary.root
        test_names = {p.name for p in root.rglob("test_*.py")}
        for rel in files:
            name = Path(rel).name
            if name in ("__init__.py", "__main__.py"):
                continue
            expected = f"test_{name}"
            if expected not in test_names:
                report.suggestions.append(Suggestion(
                    category="testing", severity=Severity.LOW,
                    message=f"no dedicated test file for {name}",
                    location=rel, action=f"add tests/{expected}",
                ))

    def _scan_maintainability(self, files: list[str], report: HealthReport) -> None:
        for rel in files:
            try:
                text = self.agent.fs.read_file(rel)
            except Exception:
                continue
            line_count = text.count("\n") + 1
            if line_count > _LARGE_FILE_LINES:
                report.suggestions.append(Suggestion(
                    category="maintainability", severity=Severity.LOW,
                    message=f"large file ({line_count} lines)",
                    location=rel, action="consider splitting into modules",
                ))
            todos = sum(1 for line in text.splitlines()
                        if "TODO" in line or "FIXME" in line)
            if todos >= _TODO_DENSITY:
                report.suggestions.append(Suggestion(
                    category="maintainability", severity=Severity.LOW,
                    message=f"{todos} TODO/FIXME markers",
                    location=rel, action="triage and resolve outstanding work",
                ))

    # ---- bounded watch mode ------------------------------------------------
    def _snapshot(self) -> dict[str, tuple[int, int]]:
        root = self.agent.boundary.root
        snap: dict[str, tuple[int, int]] = {}
        for rel in self._source_files():
            try:
                st = (root / rel).stat()
                # (mtime_ns, size) catches same-second edits and coarse-mtime
                # filesystems that a float-seconds compare would miss.
                snap[rel] = (st.st_mtime_ns, st.st_size)
            except OSError:
                continue
        return snap

    def watch(
        self,
        on_event: Callable[[WatchEvent], None] | None = None,
        poll_interval: float = 1.0,
        max_polls: int = 60,
        max_seconds: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> list[WatchEvent]:
        """Poll for source changes and proactively analyse what changed.

        Bounded by ``max_polls`` and optionally ``max_seconds`` so it always
        terminates — there is no open-ended autonomous run.
        """
        snapshot = self._snapshot()
        events: list[WatchEvent] = []
        start = clock()
        for _ in range(max_polls):
            if max_seconds is not None and clock() - start >= max_seconds:
                break
            sleep(poll_interval)
            current = self._snapshot()
            changed = [p for p, m in current.items()
                       if snapshot.get(p) != m]
            changed += [p for p in snapshot if p not in current]  # deletions
            if changed:
                report = self.analyze(paths=[p for p in changed if p in current])
                event = WatchEvent(changed=sorted(set(changed)), report=report)
                events.append(event)
                if on_event:
                    on_event(event)
            snapshot = current
        return events
