"""Multi-pass code generation.

Closes the last Phase-2 gap: turning a natural-language instruction into code.
It is deliberately the *producer* that feeds the already-built guarded pipeline
(critique -> checkpoint -> write -> verify -> rollback), so generated code is
never trusted on its own.

The generation loop:
  1. Build a focused prompt (instruction + project conventions + relevant context).
  2. Ask the model for code.
  3. Extract the code from the response.
  4. Run the deterministic SelfCritic.
  5. If the critique is blocking and passes remain, feed the findings back to the
     model for a fix pass. Otherwise return what we have, with its critique.

The system prompt encodes the hard-won lessons: no stubs/TODOs, no hardcoded
secrets, no shell=True, follow existing conventions, output only the file body.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .critic import Critique, SelfCritic
from ..llm.orchestrator import LLMOrchestrator


_SYSTEM_PROMPT = (
    "You are a senior engineer generating a single source file. Rules:\n"
    "- Output ONLY the file contents inside one fenced code block. No prose.\n"
    "- Implement fully. Do NOT leave TODO/FIXME, `pass`-only bodies, `...`, or "
    "raise NotImplementedError as placeholders.\n"
    "- Never hardcode secrets/credentials; read them from environment variables.\n"
    "- Never use eval/exec, subprocess(shell=True), os.system, or build SQL via "
    "string concatenation.\n"
    "- Match the conventions and style shown in the provided context.\n"
)

_FENCE_RE = re.compile(r"```([\w.+#-]*)[ \t]*\r?\n(.*?)```", re.DOTALL)


@dataclass
class GenerationResult:
    instruction: str
    path: str
    code: str
    passes: int
    critique: Critique
    model: str
    provider: str
    responses: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        """Code that parsed and is not blocked by critique."""
        return bool(self.code) and not self.critique.blocking


class CodeGenerator:
    def __init__(
        self,
        orchestrator: LLMOrchestrator,
        critic: SelfCritic | None = None,
        max_passes: int = 2,
    ) -> None:
        self.llm = orchestrator
        self.critic = critic or SelfCritic()
        self.max_passes = max_passes

    def generate(
        self,
        instruction: str,
        path: str,
        context: str = "",
        max_passes: int | None = None,
        model: str | None = None,
    ) -> GenerationResult:
        passes_allowed = self.max_passes if max_passes is None else max_passes
        passes_allowed = max(1, passes_allowed)
        prompt = self._build_prompt(instruction, path, context)
        responses: list[str] = []
        code = ""
        critique = Critique()
        model_used = model or self.llm.provider.name

        for attempt in range(1, passes_allowed + 1):
            response = self.llm.complete(prompt, system=_SYSTEM_PROMPT,
                                         max_tokens=2048, model=model)
            responses.append(response.text)
            model_used = response.model or model_used
            code = self._extract_code(response.text)
            critique = self.critic.review(code, filename=path)
            # Retry when the model produced no code at all (prose / no fence /
            # truncated block) OR when the critique is blocking. An empty string
            # parses as a valid empty module, so it must be treated as a retry
            # trigger explicitly rather than relying on critique.blocking.
            if code.strip() and not critique.blocking:
                break
            if attempt < passes_allowed:
                prompt = self._build_fix_prompt(instruction, path, code, critique)

        return GenerationResult(
            instruction=instruction,
            path=path,
            code=code,
            passes=len(responses),
            critique=critique,
            model=model_used,
            provider=self.llm.provider.name,
            responses=responses,
        )

    # ---- prompt construction ----------------------------------------------
    @staticmethod
    def _build_prompt(instruction: str, path: str, context: str) -> str:
        parts = [f"Task: {instruction}", f"\nTarget file: {path}"]
        if context:
            parts.append("\nRelevant project context:\n" + context)
        parts.append("\nReturn the complete contents of the target file.")
        return "\n".join(parts)

    @staticmethod
    def _build_fix_prompt(instruction: str, path: str, code: str,
                          critique: Critique) -> str:
        issues = "\n".join(
            f"- [{f.severity.name}] {f.rule}"
            + (f" (line {f.line})" if f.line else "")
            + f": {f.message}"
            for f in critique.by_severity()
        )
        syntax = "" if critique.syntax_ok else "The code does not parse. "
        return (
            f"Task: {instruction}\nTarget file: {path}\n\n"
            f"Your previous attempt had blocking issues that MUST be fixed. "
            f"{syntax}Issues:\n{issues}\n\n"
            f"Previous attempt:\n```\n{code}\n```\n\n"
            f"Return the corrected complete file contents, resolving every issue."
        )

    @staticmethod
    def _extract_code(text: str) -> str:
        """Pull the first fenced code block.

        The system prompt mandates a single fenced block, so the absence of one
        means the model did not produce code (e.g. it returned prose, or the
        offline mock provider responded). Returning an empty string here is
        deliberate: it is far safer to report "no code generated" than to write
        prose into a source file.
        """
        match = _FENCE_RE.search(text)
        if match:
            return match.group(2).rstrip("\r\n") + "\n"
        return ""
