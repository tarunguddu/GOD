"""Autonomous loop orchestration.

Implements the loop spine from the autonomous-loops patterns on top of the
GOD agent's per-iteration capabilities (plan -> generate_and_apply -> critique
-> verify -> rollback). The orchestrator owns only the concerns that a single
iteration cannot:

  - Exit conditions: max iterations, token budget, wall-clock, and a
    completion signal that must repeat N times (so one stray "done" can't stop
    a loop early).
  - Cross-iteration context: a persistent SHARED_TASK_NOTES file that bridges
    the otherwise-independent iterations (each iteration reads it, then appends
    its progress).
  - Failure-context carryover: a failed iteration's error is fed into the next
    one rather than blindly retrying the same thing.

The actual work of one iteration is a caller-supplied callable, so the loop is
both testable in isolation and reusable for different workflows.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:  # avoid a runtime import cycle (agent -> proactive -> loop)
    from .agent import GodAgent


@dataclass
class LoopLimits:
    max_runs: int = 10
    max_tokens: int | None = None        # LLM tokens consumed during THIS loop
    max_seconds: float | None = None
    completion_signal: str = "GOD_TASK_COMPLETE"
    completion_threshold: int = 2        # consecutive signals required to stop
    max_consecutive_failures: int | None = 3  # circuit breaker; None disables

    def __post_init__(self) -> None:
        if self.max_runs < 1:
            raise ValueError("max_runs must be >= 1")
        if self.completion_threshold < 1:
            raise ValueError("completion_threshold must be >= 1")
        if self.max_tokens is not None and self.max_tokens < 0:
            raise ValueError("max_tokens must be >= 0")
        if self.max_seconds is not None and self.max_seconds < 0:
            raise ValueError("max_seconds must be >= 0")
        if self.max_consecutive_failures is not None and self.max_consecutive_failures < 1:
            raise ValueError("max_consecutive_failures must be >= 1")


@dataclass
class IterationContext:
    index: int
    task: str
    notes: str
    last_error: str | None = None


@dataclass
class IterationResult:
    summary: str
    success: bool = True
    complete: bool = False               # iteration believes the task is done
    notes_update: str | None = None      # appended to SHARED_TASK_NOTES
    error: str | None = None


@dataclass
class LoopReport:
    task: str
    iterations: list[IterationResult] = field(default_factory=list)
    stopped_reason: str = ""
    completed: bool = False

    @property
    def runs(self) -> int:
        return len(self.iterations)

    def render(self) -> str:
        lines = [f"Loop: {self.task}",
                 f"  iterations: {self.runs}",
                 f"  completed:  {self.completed}",
                 f"  stopped:    {self.stopped_reason}"]
        for it in self.iterations:
            flag = "ok" if it.success else "FAIL"
            done = " [complete-signal]" if it.complete else ""
            lines.append(f"    {it.summary} ({flag}){done}")
        return "\n".join(lines)


IterationFn = Callable[[IterationContext], IterationResult]


def _is_test_path(path: str) -> bool:
    """True for test files, whose fixtures may legitimately contain sample
    'bad' code (secrets/vulns) that should not block a quality sweep."""
    norm = path.replace("\\", "/").lower()
    name = norm.rsplit("/", 1)[-1]
    parts = norm.split("/")
    return (
        "tests" in parts or "test" in parts
        or name.startswith("test_") or name.endswith("_test.py")
        or name == "conftest.py"
    )


class AutonomousLoop:
    def __init__(
        self,
        agent: GodAgent,
        limits: LoopLimits | None = None,
        notes_filename: str = "SHARED_TASK_NOTES.md",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.agent = agent
        self.limits = limits or LoopLimits()
        self.notes_path = agent.config.project_root / ".god" / notes_filename
        self._clock = clock

    # ---- notes -------------------------------------------------------------
    def read_notes(self) -> str:
        if self.notes_path.exists():
            return self.notes_path.read_text(encoding="utf-8")
        return ""

    def reset_notes(self) -> None:
        """Start a fresh notes file so a prior run cannot contaminate this one."""
        if self.notes_path.exists():
            self.notes_path.unlink()

    def _append_notes(self, index: int, text: str) -> None:
        self.notes_path.parent.mkdir(parents=True, exist_ok=True)
        header = "" if self.notes_path.exists() else "# Shared Task Notes\n\n"
        with self.notes_path.open("a", encoding="utf-8") as fh:
            fh.write(f"{header}## Iteration {index}\n{text.strip()}\n\n")

    # ---- main loop ---------------------------------------------------------
    def run(self, task: str, iteration_fn: IterationFn,
            fresh_notes: bool = True) -> LoopReport:
        report = LoopReport(task=task)
        start = self._clock()
        # Baseline so max_tokens measures spend DURING this loop, not the agent's
        # lifetime total.
        self._token_baseline = (self.agent.llm.usage.input_tokens
                                + self.agent.llm.usage.output_tokens)
        if fresh_notes:
            self.reset_notes()
        consecutive_signals = 0
        consecutive_failures = 0
        last_error: str | None = None

        for index in range(1, self.limits.max_runs + 1):
            # --- pre-iteration exit checks (budget / time) ---
            stop = self._check_resource_limits(start)
            if stop:
                report.stopped_reason = stop
                return report

            ctx = IterationContext(
                index=index, task=task, notes=self.read_notes(),
                last_error=last_error,
            )
            self.agent.safety.audit.record("loop.iteration.start", index=index, task=task)

            try:
                result = iteration_fn(ctx)
            except Exception as exc:  # an iteration must not kill the whole loop
                result = IterationResult(
                    summary=f"iteration {index} raised {type(exc).__name__}",
                    success=False, error=str(exc),
                )

            report.iterations.append(result)
            note = result.notes_update or result.summary
            self._append_notes(index, note + (f"\nERROR: {result.error}"
                                              if result.error else ""))
            last_error = result.error if not result.success else None

            self.agent.safety.audit.record(
                "loop.iteration.end", index=index, success=result.success,
                complete=result.complete,
            )

            # --- circuit breaker on repeated failure ---
            if result.success:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if (self.limits.max_consecutive_failures is not None
                        and consecutive_failures >= self.limits.max_consecutive_failures):
                    report.stopped_reason = (
                        f"aborted after {consecutive_failures} consecutive failures"
                    )
                    return report

            # --- completion-signal handling ---
            if result.complete and result.success:
                consecutive_signals += 1
                if consecutive_signals >= self.limits.completion_threshold:
                    report.completed = True
                    report.stopped_reason = (
                        f"completion signalled {consecutive_signals}x consecutively"
                    )
                    return report
            else:
                consecutive_signals = 0

        report.stopped_reason = f"reached max_runs ({self.limits.max_runs})"
        return report

    def _check_resource_limits(self, start: float) -> str | None:
        if self.limits.max_seconds is not None:
            if self._clock() - start >= self.limits.max_seconds:
                return f"reached max_seconds ({self.limits.max_seconds})"
        if self.limits.max_tokens is not None:
            baseline = getattr(self, "_token_baseline", 0)
            used = (self.agent.llm.usage.input_tokens
                    + self.agent.llm.usage.output_tokens) - baseline
            if used >= self.limits.max_tokens:
                return f"reached max_tokens ({self.limits.max_tokens}, used {used})"
        return None


# ---------------------------------------------------------------------------
# Built-in workflows (iteration_fn factories)
# ---------------------------------------------------------------------------

def quality_sweep_workflow(
    agent: GodAgent,
    verify_command: str | None = None,
) -> IterationFn:
    """A fully-deterministic (no-LLM) loop body.

    Each iteration runs verification and critiques every source file. It signals
    completion once the project both verifies and has no blocking critique
    findings. Useful as an offline quality/monitoring gate and as a way to
    exercise the loop machinery without a model.
    """
    def fn(ctx: IterationContext) -> IterationResult:
        cmd = verify_command or agent.config.test_command
        if cmd is None:
            cmd = agent.perceive().test_command
        verification = agent.verify(cmd) if cmd else None
        verified = verification.passed if verification else False

        blocking_files: list[str] = []
        review_errors: list[str] = []
        agent.perceive(refresh=True)
        for hit in agent.context.search("def class import return", top_k=200):
            if not hit.path.endswith(".py"):
                continue
            if _is_test_path(hit.path):
                continue  # test fixtures legitimately contain "bad" sample code
            try:
                critique = agent.reasoning.critic.review_file(
                    agent.boundary.check(hit.path)
                )
            except Exception as exc:
                # A file we cannot review is NOT silently treated as clean.
                review_errors.append(f"{hit.path}: {exc}")
                continue
            if critique.blocking:
                blocking_files.append(hit.path)

        clean = not blocking_files and not review_errors
        complete = verified and clean
        verdict = verification.summary if verification else "no verify command"
        summary = (f"verify={'pass' if verified else 'fail'} ({verdict}); "
                   f"blocking files={len(blocking_files)}; "
                   f"review errors={len(review_errors)}")

        if verified and clean:
            error = None
        elif not verified:
            error = f"verification: {verdict}"
        elif blocking_files:
            error = f"blocking files: {blocking_files}"
        else:
            error = f"review errors: {review_errors}"

        notes = summary
        if blocking_files:
            notes += f"\nblocking: {blocking_files}"
        if review_errors:
            notes += f"\nreview-errors: {review_errors}"
        return IterationResult(
            summary=summary,
            success=verified and clean,
            complete=complete,
            notes_update=notes,
            error=error,
        )
    return fn


def sequential_codegen_workflow(
    agent: GodAgent,
    steps: list[tuple[str, str]],
    verify_command: str | None = None,
) -> IterationFn:
    """LLM-driven sequential pipeline: one (instruction, path) step per iteration.

    Each accepted step advances; a rejected step is retried on the next
    iteration (its failure reason is carried forward via the shared notes).
    Completion is signalled once all steps are accepted.
    """
    state = {"i": 0}

    def fn(ctx: IterationContext) -> IterationResult:
        if state["i"] >= len(steps):
            return IterationResult(summary="all steps complete", complete=True)
        instruction, path = steps[state["i"]]
        outcome = agent.reasoning.generate_and_apply(
            instruction, path, verify_command=verify_command
        )
        if outcome.accepted:
            state["i"] += 1
        all_done = state["i"] >= len(steps)
        return IterationResult(
            summary=f"step {state['i']}/{len(steps)}: {instruction[:60]}",
            success=outcome.accepted,
            complete=all_done and outcome.accepted,
            notes_update=outcome.report(),
            error=None if outcome.accepted else outcome.reason,
        )
    return fn
