import pytest

from god_agent.workspace import WorkspaceBoundary, BoundaryViolation


def test_path_inside_is_allowed(project):
    b = WorkspaceBoundary(project)
    resolved = b.check("src/file.py")
    assert str(resolved).startswith(str(project))


def test_path_outside_is_blocked(project):
    b = WorkspaceBoundary(project)
    with pytest.raises(BoundaryViolation):
        b.check("../../etc/passwd")


def test_absolute_outside_blocked(project, tmp_path):
    outside = tmp_path.parent / "elsewhere"
    outside.mkdir(exist_ok=True)
    b = WorkspaceBoundary(project)
    with pytest.raises(BoundaryViolation):
        b.check(str(outside / "x.txt"))


def test_grant_extends_boundary(project, tmp_path):
    extra = tmp_path.parent / "granted"
    extra.mkdir(exist_ok=True)
    b = WorkspaceBoundary(project)
    b.grant(extra)
    assert b.is_within(extra / "ok.txt")


def test_nonexistent_root_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        WorkspaceBoundary(tmp_path / "does-not-exist")


def test_relative_display(project):
    b = WorkspaceBoundary(project)
    assert b.relative(project / "src" / "a.py") == "src/a.py".replace("/", __import__("os").sep)
