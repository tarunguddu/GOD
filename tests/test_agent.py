from god_agent.agent import GodAgent
from god_agent.config import Config


def _agent(project):
    return GodAgent(Config.load(project))


def test_perceive_detects_python(project):
    agent = _agent(project)
    ctx = agent.perceive()
    assert "python" in ctx.stacks
    assert ctx.test_command == "pytest"


def test_apply_change_with_checkpoint(project):
    agent = _agent(project)
    target = "src/feature.py"

    def mutate():
        agent.fs.write_file(target, "def feature():\n    return 1\n")

    record = agent.apply_change("add feature", [target], mutate)
    assert record.checkpoint_id
    assert agent.fs.exists(target)


def test_apply_change_rolls_back_on_error(project):
    agent = _agent(project)
    agent.fs.write_file("src/x.py", "original\n")

    def mutate():
        agent.fs.write_file("src/x.py", "broken\n")
        raise RuntimeError("boom")

    try:
        agent.apply_change("bad change", ["src/x.py"], mutate)
    except RuntimeError:
        pass
    assert agent.fs.read_file("src/x.py") == "original\n"


def test_rollback_last(project):
    agent = _agent(project)
    agent.fs.write_file("src/y.py", "v1\n")

    def mutate():
        agent.fs.write_file("src/y.py", "v2\n")

    agent.apply_change("update y", ["src/y.py"], mutate)
    assert agent.fs.read_file("src/y.py") == "v2\n"
    agent.rollback_last()
    assert agent.fs.read_file("src/y.py") == "v1\n"


def test_status_summary(project):
    agent = _agent(project)
    summary = agent.status_summary()
    assert summary["llm_provider"] == "mock"
    assert "python" in summary["stacks"]


def test_llm_mock_completion(project):
    agent = _agent(project)
    resp = agent.llm.complete("hello world")
    assert resp.provider == "mock"
    assert "mock-response" in resp.text
