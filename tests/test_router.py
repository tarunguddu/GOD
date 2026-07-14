from god_agent.llm.router import ModelRouter
from god_agent.reasoning.planner import Scope


def _router():
    return ModelRouter(fast_model="haiku", powerful_model="sonnet")


def test_exploration_routes_to_fast():
    d = _router().select("explain how the loop works")
    assert d.tier == "fast"
    assert d.model == "haiku"


def test_feature_routes_to_powerful():
    d = _router().select("add an OAuth login feature")
    assert d.tier == "powerful"
    assert d.model == "sonnet"


def test_test_scope_routes_to_fast():
    d = _router().select("write tests for the parser", scope=Scope.TEST)
    assert d.tier == "fast"


def test_long_instruction_forces_powerful():
    # A long EXPLORATION task escalates to powerful via the length signal.
    long_task = "explain " + "how this module works in detail " * 12
    d = _router().select(long_task)
    assert d.tier == "powerful"
    assert "long" in d.reason.lower()


def test_decision_has_reason():
    d = _router().select("fix the crash")
    assert d.reason
