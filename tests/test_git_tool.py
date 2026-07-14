import subprocess

import pytest

from god_agent.tools.git_tool import GitTool
from god_agent.workspace import WorkspaceBoundary


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd),
                          capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    if _git(tmp_path, "init").returncode != 0:
        pytest.skip("git not available")
    _git(tmp_path, "config", "user.email", "dev@example.com")
    _git(tmp_path, "config", "user.name", "Dev")
    return tmp_path


def _tool(repo):
    return GitTool(WorkspaceBoundary(repo))


def test_is_repo_and_branch(repo):
    tool = _tool(repo)
    assert tool.is_repo()
    # initial branch name exists after first commit
    (repo / "a.txt").write_text("1\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "init")
    assert tool.current_branch() is not None


def test_status_lists_changes(repo):
    tool = _tool(repo)
    (repo / "new.py").write_text("x = 1\n", encoding="utf-8")
    statuses = tool.status()
    assert any(s.path == "new.py" for s in statuses)


def test_stage_and_diff(repo):
    tool = _tool(repo)
    (repo / "f.py").write_text("a = 1\n", encoding="utf-8")
    assert tool.stage(["f.py"])
    diff = tool.diff(staged=True)
    assert "f.py" in diff


def test_generate_commit_message_for_additions(repo):
    tool = _tool(repo)
    (repo / "mod.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    tool.stage(["mod.py"])
    msg = tool.generate_commit_message()
    assert "feat" in msg or "chore" in msg
    assert "mod.py" in msg


def test_commit_uses_generated_message(repo):
    tool = _tool(repo)
    (repo / "x.py").write_text("y = 2\n", encoding="utf-8")
    tool.stage(["x.py"])
    ok, out = tool.commit()
    assert ok
    # the commit now exists in the log
    log = _git(repo, "log", "--oneline").stdout
    assert log.strip()


def test_no_staged_changes_message(repo):
    tool = _tool(repo)
    assert tool.generate_commit_message() == "chore: no staged changes"


def test_not_a_repo(tmp_path):
    tool = GitTool(WorkspaceBoundary(tmp_path))
    assert not tool.is_repo()
    assert tool.current_branch() is None
    assert tool.status() == []
