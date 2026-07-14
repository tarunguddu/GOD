import sys

from god_agent.agent import GodAgent
from god_agent.config import Config


def _agent(project):
    return GodAgent(Config.load(project))


def test_create_copies_sources(project):
    agent = _agent(project)
    agent.fs.write_file("src/a.py", "x = 1\n")
    sb = agent.sandbox.create()
    try:
        assert sb.file("src/a.py").exists()
        assert "src/a.py".replace("/", __import__("os").sep) in sb.manifest \
            or any(k.endswith("a.py") for k in sb.manifest)
    finally:
        agent.sandbox.destroy(sb)


def test_isolation_real_tree_untouched(project):
    agent = _agent(project)
    agent.fs.write_file("src/a.py", "original\n")
    sb = agent.sandbox.create()
    try:
        # mutate inside the sandbox only
        sb.file("src/a.py").write_text("changed in sandbox\n", encoding="utf-8")
        assert agent.fs.read_file("src/a.py") == "original\n"  # real tree intact
        diff = agent.sandbox.diff(sb)
        assert any(p.endswith("a.py") for p in diff.modified)
    finally:
        agent.sandbox.destroy(sb)


def test_run_command_in_sandbox(project):
    agent = _agent(project)
    agent.fs.write_file("src/a.py", "print('hi')\n")
    sb = agent.sandbox.create()
    try:
        # write a new file from inside the sandbox via a command
        proc = agent.sandbox.run_command(
            sb, f"{sys.executable} -c \"open('src/new.py','w').write('y = 2\\n')\"")
        assert proc.returncode == 0
        diff = agent.sandbox.diff(sb)
        assert any(p.endswith("new.py") for p in diff.created)
        # real tree must not have the new file
        assert not agent.fs.exists("src/new.py")
    finally:
        agent.sandbox.destroy(sb)


def test_promote_writes_back(project):
    agent = _agent(project)
    agent.fs.write_file("src/a.py", "original\n")
    sb = agent.sandbox.create()
    try:
        sb.file("src/a.py").write_text("improved\n", encoding="utf-8")
        sb.file("src/added.py").write_text("z = 3\n", encoding="utf-8")
        promoted = agent.sandbox.promote(sb)
        assert any(p.endswith("a.py") for p in promoted)
        assert agent.fs.read_file("src/a.py") == "improved\n"
        assert agent.fs.exists("src/added.py")
    finally:
        agent.sandbox.destroy(sb)


def test_blocked_command_refused_in_sandbox(project):
    agent = _agent(project)
    sb = agent.sandbox.create()
    try:
        try:
            agent.sandbox.run_command(sb, "rm -rf /")
            assert False, "should have raised"
        except PermissionError:
            pass
    finally:
        agent.sandbox.destroy(sb)


def test_promote_rejects_path_traversal(project):
    agent = _agent(project)
    agent.fs.write_file("src/a.py", "x = 1\n")
    sb = agent.sandbox.create()
    try:
        # A malicious explicit path must not be promoted (escapes the snapshot).
        promoted = agent.sandbox.promote(sb, paths=["../../escape.py"])
        assert promoted == []
        assert not (project.parent / "escape.py").exists()
    finally:
        agent.sandbox.destroy(sb)


def test_symlinks_are_not_snapshotted(project):
    agent = _agent(project)
    agent.fs.write_file("src/real.py", "x = 1\n")
    link = project / "src" / "link.py"
    try:
        link.symlink_to(project / "src" / "real.py")
    except (OSError, NotImplementedError):
        import pytest
        pytest.skip("symlinks not supported on this platform/permissions")
    sb = agent.sandbox.create()
    try:
        assert not sb.file("src/link.py").exists()   # symlink skipped
        assert sb.file("src/real.py").exists()
    finally:
        agent.sandbox.destroy(sb)
