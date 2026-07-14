from god_agent.safety import Decision, RiskLevel, SafetySystem
from god_agent.workspace import WorkspaceBoundary


def _safety(config):
    boundary = WorkspaceBoundary(config.project_root)
    return SafetySystem(config, boundary), boundary


def test_blocked_command_denied(config):
    safety, _ = _safety(config)
    assessment = safety.assess_command("rm -rf /")
    assert assessment.decision == Decision.DENY
    assert assessment.level == RiskLevel.CRITICAL


def test_force_push_blocked(config):
    safety, _ = _safety(config)
    assert safety.is_command_blocked("git push origin main --force")


def test_safe_command_allowed(config):
    safety, _ = _safety(config)
    assert safety.assess_command("pytest -q").decision == Decision.ALLOW


def test_side_effect_command_flagged(config):
    safety, _ = _safety(config)
    a = safety.assess_command("pip install requests")
    assert a.decision == Decision.ALLOW_WITH_CHECKPOINT


def test_delete_is_high_risk(config):
    safety, _ = _safety(config)
    a = safety.assess_file_change(["src/x.py"], deleting=True)
    assert a.level == RiskLevel.HIGH
    assert a.needs_approval is True


def test_checkpoint_and_rollback(config):
    safety, boundary = _safety(config)
    target = config.project_root / "src" / "data.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("original", encoding="utf-8")

    cp = safety.create_checkpoint([str(target)], label="test")
    target.write_text("modified", encoding="utf-8")
    assert target.read_text(encoding="utf-8") == "modified"

    safety.rollback(cp)
    assert target.read_text(encoding="utf-8") == "original"


def test_rollback_removes_created_file(config):
    safety, _ = _safety(config)
    new_file = config.project_root / "src" / "new.txt"
    new_file.parent.mkdir(parents=True, exist_ok=True)

    cp = safety.create_checkpoint([str(new_file)], label="pre-create")
    new_file.write_text("created after checkpoint", encoding="utf-8")
    assert new_file.exists()

    safety.rollback(cp)
    assert not new_file.exists()


def test_audit_log_records(config):
    safety, _ = _safety(config)
    safety.audit.record("test.event", foo="bar")
    tail = safety.audit.tail(5)
    assert any(e["event"] == "test.event" for e in tail)
