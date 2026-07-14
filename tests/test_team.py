from god_agent import team
from god_agent.agent import GodAgent
from god_agent.config import Config
from god_agent.memory.episodic import Episode


def _agent(project):
    return GodAgent(Config.load(project))


def test_export_then_import_bundle(tmp_path):
    # source project learns something
    src_proj = tmp_path / "src_proj"
    src_proj.mkdir()
    (src_proj / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (src_proj / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    src = GodAgent(Config.load(src_proj))
    src.memory.learn_conventions(force=True)
    src.memory.record_episode(Episode(task="add key", accepted=False,
                                       critique_rules=["secret:aws-access-key"]))
    bundle_path = str(src_proj / "knowledge.json")
    team.export_bundle(src, bundle_path)

    # destination project (fresh) imports it
    dst_proj = tmp_path / "dst_proj"
    dst_proj.mkdir()
    (dst_proj / "pyproject.toml").write_text("[project]\nname='y'\n", encoding="utf-8")
    dst = GodAgent(Config.load(dst_proj))
    # copy bundle into dst boundary
    (dst_proj / "knowledge.json").write_text(
        (src_proj / "knowledge.json").read_text(encoding="utf-8"), encoding="utf-8")
    imported = team.import_bundle(dst, "knowledge.json")
    assert imported == 1
    # the imported lesson now surfaces in guidance
    guidance = dst.memory.guidance_for("add another key")
    assert "environment" in guidance.lower()


def test_onboarding_doc_contains_sections(project):
    agent = _agent(project)
    agent.fs.write_file("src/widget.py",
                        "class Widget:\n    def build(self):\n        return 1\n")
    doc = team.generate_onboarding(agent)
    assert "# Onboarding" in doc
    assert "Tech stack" in doc
    assert "Module map" in doc
    assert "widget.py" in doc


def test_import_rejects_non_mapping(project):
    agent = _agent(project)
    import pytest
    with pytest.raises(ValueError):
        agent.memory.import_bundle([1, 2, 3])


def test_import_rejects_oversized_bundle(project, monkeypatch):
    agent = _agent(project)
    import pytest
    import god_agent.team as team_mod
    monkeypatch.setattr(team_mod, "_MAX_BUNDLE_BYTES", 10)
    agent.fs.write_file("big.json", '{"version": 1, "episodes": []}')  # > 10 bytes
    with pytest.raises(ValueError):
        team.import_bundle(agent, "big.json")
