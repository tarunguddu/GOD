import subprocess

import pytest

from god_agent.tools.git_tool import GitTool
from god_agent.workspace import WorkspaceBoundary


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd),
                          capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path):
    if _git(tmp_path, "init").returncode != 0:
        pytest.skip("git not available")
    _git(tmp_path, "config", "user.email", "dev@example.com")
    _git(tmp_path, "config", "user.name", "Test Dev")
    (tmp_path / "mod.py").write_text("x = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "mod.py")
    _git(tmp_path, "commit", "-m", "init mod")
    (tmp_path / "mod.py").write_text("x = 2\n", encoding="utf-8")
    _git(tmp_path, "add", "mod.py")
    _git(tmp_path, "commit", "-m", "update mod")
    return tmp_path


def test_find_who_knows(git_repo):
    tool = GitTool(WorkspaceBoundary(git_repo))
    owners = tool.find_who_knows("mod.py")
    assert owners
    assert owners[0][0] == "Test Dev"
    assert owners[0][1] == 2          # two commits touched the file


def test_find_who_knows_untracked(git_repo):
    tool = GitTool(WorkspaceBoundary(git_repo))
    (git_repo / "new.py").write_text("y = 1\n", encoding="utf-8")
    assert tool.find_who_knows("new.py") == []
