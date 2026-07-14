from god_agent.memory.episodic import Episode
from god_agent.memory.skills import Skill, SkillStore
from god_agent.memory.system import MemorySystem


# ---- SkillStore.derive -----------------------------------------------------
def test_skills_only_count_successful_episodes():
    """A skill is a repeated success: accepted AND verified. Others are ignored."""
    eps = [
        Episode(task="add test for parser", accepted=True, verified=True),
        Episode(task="add test for loader", accepted=True, verified=True),
        Episode(task="add test that failed", accepted=True, verified=False),
        Episode(task="add test rejected", accepted=False, verified=True),
    ]
    skills = SkillStore().derive(eps)
    test_skill = next(s for s in skills if s.pattern == "test")
    assert test_skill.count == 2  # only the two accepted+verified episodes


def test_skills_ranked_by_count():
    eps = [
        Episode(task="refactor module a", accepted=True, verified=True),
        Episode(task="refactor module b", accepted=True, verified=True),
        Episode(task="document the api", accepted=True, verified=True),
    ]
    skills = SkillStore().derive(eps)
    assert skills[0].pattern == "refactor"
    assert skills[0].count == 2


def test_skills_capture_example_paths():
    eps = [
        Episode(task="fix bug in auth", path="auth.py", accepted=True, verified=True),
    ]
    skills = SkillStore().derive(eps)
    fix_skill = next(s for s in skills if s.pattern == "fix")
    assert "auth.py" in fix_skill.paths


def test_skills_capture_example_task_descriptions():
    eps = [
        Episode(task="fix login crash", path="auth.py", accepted=True, verified=True),
    ]
    skills = SkillStore().derive(eps)
    fix_skill = next(s for s in skills if s.pattern == "fix")
    assert "fix login crash" in fix_skill.examples


def test_examples_and_paths_are_unique_and_capped():
    # Six successful "test" episodes with duplicate paths should not bloat.
    eps = [
        Episode(task=f"add test number {i}", path="tests/test_x.py",
                accepted=True, verified=True)
        for i in range(6)
    ]
    skill = SkillStore().derive(eps)[0]
    assert skill.count == 6                 # every success still counted
    assert len(skill.examples) <= 3         # examples capped for compact guidance
    assert skill.paths == ["tests/test_x.py"]  # duplicate paths collapsed


def test_uncategorizable_tasks_produce_no_skill():
    eps = [Episode(task="zzz qqq", accepted=True, verified=True)]
    assert SkillStore().derive(eps) == []


def test_min_count_filters_rare_skills():
    eps = [Episode(task="add feature x", accepted=True, verified=True)]
    assert SkillStore().derive(eps, min_count=2) == []


def test_skill_render_is_positive_and_mentions_count():
    skill = Skill(pattern="test", count=3, advice="Reuse the proven testing approach.",
                  examples=["add test for parser"], paths=["tests/test_x.py"])
    rendered = skill.render()
    assert "3x" in rendered
    assert "test" in rendered.lower()


def test_skill_render_surfaces_a_concrete_example():
    skill = Skill(pattern="fix", count=2, advice="Apply the same focused fix.",
                  examples=["fix login crash"], paths=["auth.py"])
    rendered = skill.render()
    assert "fix login crash" in rendered
    assert "auth.py" in rendered


# ---- MemorySystem integration ---------------------------------------------
def test_top_skills_via_memory_system(tmp_path):
    sys = MemorySystem(tmp_path)
    sys.record_episode(Episode(task="implement login", accepted=True, verified=True))
    sys.record_episode(Episode(task="implement logout", accepted=True, verified=True))
    skills = sys.top_skills(n=5)
    assert any(s.pattern == "implement" for s in skills)


def test_relevant_skills_prefers_similar_tasks(tmp_path):
    sys = MemorySystem(tmp_path)
    sys.record_episode(Episode(task="add yaml config parser",
                               accepted=True, verified=True))
    sys.record_episode(Episode(task="optimize render loop performance",
                               accepted=True, verified=True))
    skills = sys.relevant_skills("add yaml settings parser", n=3)
    assert any(s.pattern == "add" for s in skills)


def test_guidance_includes_proven_approaches(tmp_path):
    sys = MemorySystem(tmp_path)
    sys.record_episode(Episode(task="refactor the payment module",
                               accepted=True, verified=True))
    guidance = sys.guidance_for("refactor the billing module")
    assert "proven" in guidance.lower()


def test_guidance_empty_when_nothing_learned(tmp_path):
    sys = MemorySystem(tmp_path)
    assert sys.guidance_for("do something new") == ""


def test_failures_do_not_create_skills(tmp_path):
    sys = MemorySystem(tmp_path)
    sys.record_episode(Episode(task="fix the crash", accepted=False, verified=False))
    assert sys.top_skills() == []
