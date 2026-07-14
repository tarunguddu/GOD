import pytest

from god_agent.safety import SafetySystem
from god_agent.tools.filesystem import FileSystemTool
from god_agent.workspace import WorkspaceBoundary


@pytest.fixture
def fs(config):
    boundary = WorkspaceBoundary(config.project_root)
    safety = SafetySystem(config, boundary)
    return FileSystemTool(boundary, safety)


def test_write_then_read(fs):
    res = fs.write_file("src/hello.py", "print('hi')\n")
    assert res.created is True
    assert fs.read_file("src/hello.py") == "print('hi')\n"


def test_write_creates_backup_on_overwrite(fs):
    fs.write_file("src/a.txt", "v1")
    res = fs.write_file("src/a.txt", "v2")
    assert res.created is False
    assert res.backup is not None
    assert fs.read_file("src/a.txt") == "v2"


def test_edit_replaces(fs):
    fs.write_file("src/m.py", "x = 1\ny = 2\n")
    res = fs.edit_file("src/m.py", "x = 1", "x = 42")
    assert res.replacements == 1
    assert "x = 42" in fs.read_file("src/m.py")


def test_edit_missing_target_raises(fs):
    fs.write_file("src/m.py", "a = 1\n")
    with pytest.raises(ValueError):
        fs.edit_file("src/m.py", "nonexistent", "z")


def test_delete_requires_approval(fs):
    fs.write_file("src/del.py", "1")
    with pytest.raises(PermissionError):
        fs.delete_file("src/del.py")
    assert fs.delete_file("src/del.py", approved=True) is True
    assert fs.exists("src/del.py") is False
