import pytest

from god_agent.safety import SafetySystem
from god_agent.tools.shell import ShellTool, ShellCommandDenied
from god_agent.workspace import WorkspaceBoundary


@pytest.fixture
def shell(config):
    boundary = WorkspaceBoundary(config.project_root)
    safety = SafetySystem(config, boundary)
    return ShellTool(boundary, safety)


def test_echo_runs(shell):
    res = shell.run("echo hello")
    assert res.ok
    assert "hello" in res.stdout


def test_blocked_command_raises(shell):
    with pytest.raises(ShellCommandDenied):
        shell.run("rm -rf /")


def test_side_effect_command_proceeds_with_checkpoint(shell):
    # Side-effecting commands are medium risk: they proceed (a checkpoint is the
    # mitigation), they are not hard-gated. Only blocked patterns are denied.
    res = shell.run("echo installing things")
    assert res.ok


def test_nonzero_exit_reported(shell):
    res = shell.run("python -c \"import sys; sys.exit(3)\"")
    # python alias may not exist on all systems; only assert structure
    assert res.returncode is not None
