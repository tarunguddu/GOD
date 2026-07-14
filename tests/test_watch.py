from god_agent.agent import GodAgent
from god_agent.config import Config


def _agent(project):
    return GodAgent(Config.load(project))


def test_watch_terminates_at_max_polls(project):
    agent = _agent(project)
    agent.fs.write_file("src/a.py", "x = 1\n")
    # no changes happen; fake sleep/clock so the test is instant
    events = agent.proactive.watch(
        poll_interval=0, max_polls=3, sleep=lambda s: None, clock=lambda: 0.0)
    assert events == []


def test_watch_detects_change(project):
    agent = _agent(project)
    agent.fs.write_file("src/a.py", "x = 1\n")

    # Mutate the file on the first sleep so the next snapshot differs.
    state = {"polls": 0}

    def fake_sleep(_):
        state["polls"] += 1
        if state["polls"] == 1:
            agent.fs.write_file("src/a.py", "def e(s):\n    return eval(s)\n")

    events = agent.proactive.watch(
        poll_interval=0, max_polls=3, sleep=fake_sleep, clock=lambda: 0.0)
    assert events
    assert any("a.py" in c for c in events[0].changed)
    # the changed file is analysed, surfacing the eval finding
    assert any(s.category == "security" for s in events[0].report.suggestions)


def test_watch_max_seconds(project):
    agent = _agent(project)
    agent.fs.write_file("src/a.py", "x = 1\n")
    ticks = iter([0, 0, 10, 20, 30])
    events = agent.proactive.watch(
        poll_interval=0, max_polls=100, max_seconds=5,
        sleep=lambda s: None, clock=lambda: next(ticks))
    assert events == []  # exits on time bound, no changes
