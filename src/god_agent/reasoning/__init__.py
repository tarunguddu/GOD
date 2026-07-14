"""Reasoning engine — the thinking core.

Turns a request into a structured plan, critically reviews both the plan and any
generated code (deterministically, so it works offline), executes with safety
checkpoints, and verifies the result before reporting success.
"""

from .critic import SelfCritic, Critique, Finding, Severity
from .planner import TaskPlanner, ExecutionPlan, PlanStep, StepType, Scope
from .generator import CodeGenerator, GenerationResult
from .engine import ReasoningEngine, ReasoningOutcome

__all__ = [
    "SelfCritic",
    "Critique",
    "Finding",
    "Severity",
    "TaskPlanner",
    "ExecutionPlan",
    "PlanStep",
    "StepType",
    "Scope",
    "CodeGenerator",
    "GenerationResult",
    "ReasoningEngine",
    "ReasoningOutcome",
]
