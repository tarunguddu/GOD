"""Task-aware model routing.

Addresses the "model lock-in / no routing flexibility" reality: route trivial,
read-mostly work to a cheaper/faster model and complex multi-file work to a more
capable one, deliberately rather than defaulting everything to one model.

The router is advisory — it returns a ``(tier, model)`` decision. Whether a
second provider is actually wired in is a deployment choice; the decision logic
lives here, is deterministic, and is unit-tested.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..reasoning.planner import Scope, TaskPlanner


@dataclass(frozen=True)
class RouteDecision:
    tier: str          # "fast" | "powerful"
    model: str
    reason: str


# Scopes that are typically light enough for the fast model.
_FAST_SCOPES = {Scope.EXPLORATION, Scope.TEST}

# A long / multi-file instruction warrants the powerful model regardless.
_COMPLEX_LENGTH = 180


class ModelRouter:
    def __init__(self, fast_model: str, powerful_model: str,
                 planner: TaskPlanner | None = None) -> None:
        self.fast_model = fast_model
        self.powerful_model = powerful_model
        self.planner = planner or TaskPlanner()

    def select(self, task: str, scope: Scope | None = None) -> RouteDecision:
        scope = scope or self.planner.classify(task)
        # Scope is the primary signal. Length only *escalates* a fast-scope task
        # to the capable model when the instruction is also large; it never
        # forces a clearly-complex (non-fast) scope down, nor flips on length
        # alone for trivial work.
        if scope in _FAST_SCOPES:
            if len(task) >= _COMPLEX_LENGTH:
                return RouteDecision(
                    "powerful", self.powerful_model,
                    f"{scope.value} but long ({len(task)} chars) — escalating")
            return RouteDecision("fast", self.fast_model,
                                 f"{scope.value} work routes to the fast model")
        return RouteDecision("powerful", self.powerful_model,
                             f"{scope.value} work routes to the capable model")
