"""Reasoning engine — orchestrates plan -> critique -> act -> verify -> report.

The headline capability is :meth:`ReasoningEngine.safe_apply`: a guarded write
pipeline that embodies the project's entire philosophy in one call:

    1. CRITIQUE the proposed code *before* writing it. Blocking findings
       (syntax errors, secrets, high-severity vulns) abort the write entirely —
       bad code never lands on disk.
    2. CHECKPOINT then write (reversible).
    3. VERIFY by running the real test command and parsing the result.
    4. ROLLBACK automatically if verification fails.
    5. Report an honest outcome that distinguishes "verified" from "unverified".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .critic import Critique, SelfCritic
from .generator import CodeGenerator, GenerationResult
from .planner import ExecutionPlan, Scope, TaskPlanner
from ..memory.episodic import Episode
from ..verify import VerificationResult

if TYPE_CHECKING:  # avoid a runtime import cycle
    from ..agent import GodAgent


@dataclass
class ReasoningOutcome:
    accepted: bool
    description: str
    path: str | None = None
    critique: Critique | None = None
    verification: VerificationResult | None = None
    rolled_back: bool = False
    reason: str = ""

    def report(self) -> str:
        lines = [f"{'ACCEPTED' if self.accepted else 'REJECTED'}: {self.description}"]
        if self.path:
            lines.append(f"  path: {self.path}")
        if self.critique is not None:
            lines.append(f"  review: {self.critique.summary()}")
        if self.verification is not None:
            lines.append(f"  {self.verification.as_claim()}")
        if self.rolled_back:
            lines.append("  rolled back to pre-change state")
        if self.reason:
            lines.append(f"  reason: {self.reason}")
        return "\n".join(lines)


class ReasoningEngine:
    def __init__(self, agent: "GodAgent") -> None:
        self.agent = agent
        self.planner = TaskPlanner()
        self.critic = SelfCritic()
        self.generator = CodeGenerator(agent.llm, self.critic)

    # ---- planning ----------------------------------------------------------
    def plan(self, request: str, scope: Scope | None = None) -> ExecutionPlan:
        return self.planner.create_plan(request, scope)

    def critique_code(self, code: str, filename: str = "<generated>") -> Critique:
        return self.critic.review(code, filename)

    # ---- guarded write -----------------------------------------------------
    def safe_apply(
        self,
        description: str,
        path: str,
        content: str,
        verify_command: str | None = None,
        allow_findings: bool = False,
    ) -> ReasoningOutcome:
        """Critique, then write behind a checkpoint, then verify, rolling back
        on failure.

        Set ``allow_findings=True`` to proceed past blocking critique findings
        (still checkpointed and verified) — an explicit, auditable override.
        """
        critique = self.critic.review(content, filename=path)

        if critique.blocking:
            blocking_rules = [f.rule for f in critique.findings if f.severity >= 3]
            if not allow_findings:
                self.agent.safety.audit.record(
                    "reasoning.reject", path=path, reason="critique-blocking",
                    findings=blocking_rules,
                )
                self._remember(description, path, accepted=False,
                               critique=critique, verification=None)
                return ReasoningOutcome(
                    accepted=False, description=description, path=path,
                    critique=critique,
                    reason=f"blocked by self-critique ({critique.summary()}); "
                           f"code was NOT written.",
                )
            # Explicit, audited override: a human/caller chose to proceed past
            # blocking findings. This MUST leave a trail.
            self.agent.safety.audit.record(
                "reasoning.override", path=path, reason="allow_findings",
                bypassed=blocking_rules, summary=critique.summary(),
            )

        # checkpoint + write
        record = self.agent.apply_change(
            description, [path], lambda: self.agent.fs.write_file(path, content)
        )

        # verify
        verification: VerificationResult | None = None
        cmd = verify_command or self.agent.config.test_command
        if cmd is None:
            project = self.agent.perceive()
            cmd = project.test_command
        if cmd:
            verification = self.agent.verify(cmd)
            record.verified = verification
            if not verification.passed:
                self.agent.rollback_last()
                self.agent.safety.audit.record(
                    "reasoning.rollback", path=path,
                    reason="verification-failed", verdict=verification.summary,
                )
                self._remember(description, path, accepted=False,
                               critique=critique, verification=verification)
                return ReasoningOutcome(
                    accepted=False, description=description, path=path,
                    critique=critique, verification=verification, rolled_back=True,
                    reason="verification failed; change reverted.",
                )

        self._remember(description, path, accepted=True,
                       critique=critique, verification=verification)
        return ReasoningOutcome(
            accepted=True, description=description, path=path,
            critique=critique, verification=verification,
            reason="" if verification else "no verification command available — "
                   "change applied but UNVERIFIED.",
        )

    def _remember(self, task: str, path: str, accepted: bool,
                  critique: Critique | None,
                  verification: VerificationResult | None) -> None:
        """Record an episode so the agent learns from this outcome."""
        try:
            rules = [f.rule for f in critique.findings] if critique else []
            self.agent.memory.record_episode(Episode(
                task=task, path=path, accepted=accepted,
                critique_rules=rules,
                verified=(verification.passed if verification else None),
                verdict=(verification.summary if verification else ""),
            ))
        except Exception:
            # Memory must never break the primary workflow.
            pass

    # ---- generation -> guarded write --------------------------------------
    def generate_and_apply(
        self,
        instruction: str,
        path: str,
        verify_command: str | None = None,
        context_query: str | None = None,
        max_passes: int = 2,
    ) -> ReasoningOutcome:
        """Generate code for ``instruction`` and run it through ``safe_apply``.

        Relevant project context is gathered via the context engine's search and
        fed to the generator. The generated code still passes through the full
        guarded pipeline — it is never written or trusted without critique and
        verification.
        """
        context = self._gather_context(context_query or instruction)
        # Closing the loop: prepend learned conventions + lessons so the model's
        # output reflects this project's style and past mistakes.
        try:
            guidance = self.agent.memory.guidance_for(instruction)
        except Exception:
            guidance = ""
        if guidance:
            context = guidance + ("\n\n" + context if context else "")
        # Route to a model tier based on the task (advisory; honoured when a
        # provider supports per-request model selection).
        try:
            route = self.agent.router.select(instruction)
            model = route.model
        except Exception:
            model = None
        result = self.generator.generate(instruction, path, context=context,
                                          max_passes=max_passes, model=model)

        if not result.code:
            return ReasoningOutcome(
                accepted=False, description=instruction, path=path,
                critique=result.critique,
                reason=f"generation produced no usable code (provider="
                       f"{result.provider}). With the mock provider this is "
                       f"expected; configure a real LLM provider.",
            )

        outcome = self.safe_apply(
            description=instruction, path=path, content=result.code,
            verify_command=verify_command,
        )
        # Surface generation metadata on the outcome's reason for transparency.
        meta = f" [generated in {result.passes} pass(es) via {result.provider}]"
        outcome.reason = (outcome.reason + meta).strip()
        return outcome

    def _gather_context(self, query: str, top_k: int = 4, max_chars: int = 4000) -> str:
        """Build a compact, token-budgeted context block from relevant files."""
        try:
            self.agent.perceive()
            hits = self.agent.context.search(query, top_k=top_k)
        except Exception:
            return ""
        blocks: list[str] = []
        budget = max_chars
        for hit in hits:
            try:
                content = self.agent.fs.read_file(hit.path)
            except Exception:
                continue
            snippet = content[: min(len(content), 1200)]
            block = f"# file: {hit.path}\n{snippet}"
            if len(block) > budget:
                break
            blocks.append(block)
            budget -= len(block)
        return "\n\n".join(blocks)
