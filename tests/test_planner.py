from god_agent.reasoning.planner import Scope, StepType, TaskPlanner


def test_classify_feature():
    assert TaskPlanner().classify("add a login endpoint") == Scope.FEATURE


def test_classify_bugfix():
    assert TaskPlanner().classify("fix the crash on startup") == Scope.BUGFIX


def test_classify_refactor():
    assert TaskPlanner().classify("refactor the auth module") == Scope.REFACTOR


def test_classify_exploration():
    assert TaskPlanner().classify("explain how routing works") == Scope.EXPLORATION


def test_every_mutating_plan_has_verify():
    planner = TaskPlanner()
    for request in ("add feature x", "fix bug y", "refactor z", "write tests for w"):
        plan = planner.create_plan(request)
        assert plan.has_verification, f"{plan.scope} missing VERIFY step"


def test_exploration_plan_has_no_mutation():
    plan = TaskPlanner().create_plan("explain the codebase")
    types = {s.type for s in plan.steps}
    assert StepType.IMPLEMENT not in types


def test_plan_renders():
    plan = TaskPlanner().create_plan("add a feature")
    text = plan.render()
    assert "Plan" in text and "verify" in text.lower()
