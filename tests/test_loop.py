from god_agent.agent import GodAgent
from god_agent.config import Config
from god_agent.loop import (
    AutonomousLoop,
    IterationContext,
    IterationResult,
    LoopLimits,
)


def _agent(project):
    return GodAgent(Config.load(project))


def test_stops_at_max_runs(project):
    loop = AutonomousLoop(_agent(project), LoopLimits(max_runs=3))
    report = loop.run("task", lambda ctx: IterationResult(summary=f"i{ctx.index}"))
    assert report.runs == 3
    assert "max_runs" in report.stopped_reason
    assert not report.completed


def test_completion_signal_requires_threshold(project):
    loop = AutonomousLoop(_agent(project),
                          LoopLimits(max_runs=10, completion_threshold=2))

    def fn(ctx: IterationContext) -> IterationResult:
        return IterationResult(summary=f"i{ctx.index}", complete=True)

    report = loop.run("task", fn)
    assert report.completed
    assert report.runs == 2          # two consecutive signals -> stop


def test_single_signal_does_not_stop(project):
    loop = AutonomousLoop(_agent(project),
                          LoopLimits(max_runs=4, completion_threshold=2))
    seq = iter([True, False, True, True])

    def fn(ctx):
        return IterationResult(summary=f"i{ctx.index}", complete=next(seq))

    report = loop.run("task", fn)
    # signals: T(1), F(reset), T(1), T(2)->stop at iteration 4
    assert report.runs == 4
    assert report.completed


def test_max_seconds_exit(project):
    # fake clock advances 10s per call
    times = iter([0, 0, 10, 20, 30, 40, 50])
    loop = AutonomousLoop(_agent(project), LoopLimits(max_runs=100, max_seconds=5),
                          clock=lambda: next(times))
    report = loop.run("task", lambda ctx: IterationResult(summary="x"))
    assert "max_seconds" in report.stopped_reason


def test_max_tokens_exit(project):
    agent = _agent(project)
    agent.llm.usage.input_tokens = 1000  # pre-existing spend must NOT count
    loop = AutonomousLoop(agent, LoopLimits(max_runs=100, max_tokens=500))

    # Each iteration "spends" 200 tokens; budget is measured from loop start.
    def spend(ctx):
        agent.llm.usage.output_tokens += 200
        return IterationResult(summary=f"i{ctx.index}")

    report = loop.run("task", spend)
    assert "max_tokens" in report.stopped_reason
    # baseline=1000; exits once 500 spent during the loop (after ~3 iterations)
    assert report.runs <= 4


def test_exception_in_iteration_does_not_kill_loop(project):
    loop = AutonomousLoop(_agent(project), LoopLimits(max_runs=2))

    def boom(ctx):
        raise RuntimeError("kaboom")

    report = loop.run("task", boom)
    assert report.runs == 2
    assert all(not it.success for it in report.iterations)
    assert "kaboom" in (report.iterations[0].error or "")


def test_notes_persist_across_iterations(project):
    loop = AutonomousLoop(_agent(project), LoopLimits(max_runs=3))
    seen_notes = []

    def fn(ctx: IterationContext) -> IterationResult:
        seen_notes.append(ctx.notes)
        return IterationResult(summary=f"did step {ctx.index}",
                               notes_update=f"progress {ctx.index}")

    loop.run("task", fn)
    # first iteration sees empty notes; later ones see accumulated notes
    assert seen_notes[0] == ""
    assert "progress 1" in seen_notes[1]
    assert "progress 1" in seen_notes[2] and "progress 2" in seen_notes[2]
    assert loop.notes_path.exists()


def test_last_error_carried_forward(project):
    loop = AutonomousLoop(_agent(project), LoopLimits(max_runs=3))
    errors_seen = []

    def fn(ctx: IterationContext) -> IterationResult:
        errors_seen.append(ctx.last_error)
        if ctx.index == 1:
            return IterationResult(summary="fail", success=False, error="boom1")
        return IterationResult(summary="ok")

    loop.run("task", fn)
    assert errors_seen[0] is None
    assert errors_seen[1] == "boom1"     # error from iteration 1 carried in
    assert errors_seen[2] is None        # iteration 2 succeeded -> cleared


def test_circuit_breaker_aborts_on_consecutive_failures(project):
    loop = AutonomousLoop(
        _agent(project),
        LoopLimits(max_runs=20, max_consecutive_failures=3),
    )

    def always_fail(ctx):
        return IterationResult(summary="nope", success=False, error="x")

    report = loop.run("task", always_fail)
    assert report.runs == 3
    assert "consecutive failures" in report.stopped_reason


def test_circuit_breaker_resets_on_success(project):
    loop = AutonomousLoop(
        _agent(project),
        LoopLimits(max_runs=6, max_consecutive_failures=3),
    )
    # fail, fail, succeed, fail, fail, fail -> aborts at run 6 (3 in a row)
    seq = iter([False, False, True, False, False, False])

    def fn(ctx):
        ok = next(seq)
        return IterationResult(summary="s", success=ok, error=None if ok else "e")

    report = loop.run("task", fn)
    assert report.runs == 6
    assert "consecutive failures" in report.stopped_reason


def test_invalid_limits_rejected():
    import pytest
    with pytest.raises(ValueError):
        LoopLimits(max_runs=0)
    with pytest.raises(ValueError):
        LoopLimits(completion_threshold=0)


def test_notes_reset_between_runs(project):
    loop = AutonomousLoop(_agent(project), LoopLimits(max_runs=1))
    loop.run("first", lambda ctx: IterationResult(summary="run-one-note"))
    # second run with fresh_notes (default) must not see the first run's notes
    seen = []
    loop.run("second", lambda ctx: seen.append(ctx.notes) or
             IterationResult(summary="run-two"))
    assert "run-one-note" not in seen[0]
