"""Task planning and decomposition.

Classifies a request into a scope and produces a structured, ordered plan with
explicit validation and rollback intent. The plan templates are deterministic
(no model needed); an LLM can later enrich step detail, but the spine — and in
particular the mandatory ``VERIFY`` step — is fixed in code so it can never be
skipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Scope(str, Enum):
    FEATURE = "feature"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    TEST = "test"
    EXPLORATION = "exploration"


class StepType(str, Enum):
    ANALYZE = "analyze"
    DESIGN = "design"
    IMPLEMENT = "implement"
    VERIFY = "verify"
    REVIEW = "review"
    DOCUMENT = "document"


@dataclass
class PlanStep:
    type: StepType
    description: str
    requires_approval: bool = False


@dataclass
class ExecutionPlan:
    scope: Scope
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    rollback_strategy: str = "checkpoint before each mutating step; restore on failure"

    @property
    def has_verification(self) -> bool:
        return any(s.type == StepType.VERIFY for s in self.steps)

    def render(self) -> str:
        lines = [f"Plan ({self.scope.value}): {self.goal}", ""]
        for i, step in enumerate(self.steps, 1):
            flag = "  [approval]" if step.requires_approval else ""
            lines.append(f"  {i}. [{step.type.value}] {step.description}{flag}")
        lines.append("")
        lines.append(f"rollback: {self.rollback_strategy}")
        return "\n".join(lines)


# keyword -> scope (first match wins, order matters)
_SCOPE_KEYWORDS: list[tuple[Scope, tuple[str, ...]]] = [
    (Scope.BUGFIX, ("fix", "bug", "broken", "error", "crash", "regression", "fails")),
    (Scope.REFACTOR, ("refactor", "rename", "clean up", "cleanup", "restructure",
                      "extract", "simplify", "deduplicate")),
    (Scope.TEST, ("test", "coverage", "unit test", "spec")),
    (Scope.EXPLORATION, ("explain", "understand", "explore", "investigate",
                         "how does", "what is", "analyze", "review")),
    (Scope.FEATURE, ("add", "implement", "create", "build", "support", "introduce",
                     "feature")),
]


class TaskPlanner:
    def classify(self, request: str) -> Scope:
        low = request.lower()
        for scope, keywords in _SCOPE_KEYWORDS:
            if any(k in low for k in keywords):
                return scope
        return Scope.FEATURE

    def create_plan(self, request: str, scope: Scope | None = None) -> ExecutionPlan:
        scope = scope or self.classify(request)
        builder = {
            Scope.FEATURE: self._feature,
            Scope.BUGFIX: self._bugfix,
            Scope.REFACTOR: self._refactor,
            Scope.TEST: self._test,
            Scope.EXPLORATION: self._exploration,
        }[scope]
        return ExecutionPlan(scope=scope, goal=request.strip(), steps=builder())

    # ---- templates ---------------------------------------------------------
    def _feature(self) -> list[PlanStep]:
        return [
            PlanStep(StepType.ANALYZE, "Locate integration points via code graph + search"),
            PlanStep(StepType.DESIGN, "Define interfaces/types before implementation"),
            PlanStep(StepType.IMPLEMENT, "Implement core logic behind a safety checkpoint"),
            PlanStep(StepType.REVIEW, "Self-critique generated code (secrets, vulns, stubs)"),
            PlanStep(StepType.IMPLEMENT, "Add/extend tests covering the new behaviour"),
            PlanStep(StepType.VERIFY, "Run the test suite and parse the real result"),
            PlanStep(StepType.DOCUMENT, "Update docs/README if public surface changed"),
        ]

    def _bugfix(self) -> list[PlanStep]:
        return [
            PlanStep(StepType.ANALYZE, "Reproduce and locate the defect; impact analysis"),
            PlanStep(StepType.IMPLEMENT, "Apply the minimal fix behind a checkpoint"),
            PlanStep(StepType.REVIEW, "Self-critique the change"),
            PlanStep(StepType.IMPLEMENT, "Add a regression test that fails before the fix"),
            PlanStep(StepType.VERIFY, "Run tests; confirm the regression test passes"),
        ]

    def _refactor(self) -> list[PlanStep]:
        return [
            PlanStep(StepType.ANALYZE, "Map callers/impact of the symbols to change"),
            PlanStep(StepType.VERIFY, "Capture a green baseline before touching anything"),
            PlanStep(StepType.IMPLEMENT, "Refactor in small steps behind a checkpoint"),
            PlanStep(StepType.REVIEW, "Self-critique; ensure behaviour is preserved"),
            PlanStep(StepType.VERIFY, "Re-run tests; output must match the baseline"),
        ]

    def _test(self) -> list[PlanStep]:
        return [
            PlanStep(StepType.ANALYZE, "Identify under-tested code via complexity hotspots"),
            PlanStep(StepType.IMPLEMENT, "Write tests for the highest-risk paths"),
            PlanStep(StepType.VERIFY, "Run the new tests and confirm they pass honestly"),
        ]

    def _exploration(self) -> list[PlanStep]:
        return [
            PlanStep(StepType.ANALYZE, "Build project context and code graph"),
            PlanStep(StepType.REVIEW, "Summarise structure, hotspots, and relevant files"),
        ]
