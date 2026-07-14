from god_agent.memory.conventions import ConventionDetector
from god_agent.memory.episodic import Episode, EpisodicMemory
from god_agent.memory.lessons import LessonStore
from god_agent.memory.system import MemorySystem


# ---- episodic --------------------------------------------------------------
def test_episode_roundtrip(tmp_path):
    mem = EpisodicMemory(tmp_path / "ep.jsonl")
    mem.record(Episode(task="add login", path="a.py", accepted=True,
                       critique_rules=["smell:bare-except"], verified=True,
                       verdict="3 passing"))
    loaded = mem.all()
    assert len(loaded) == 1
    assert loaded[0].task == "add login"
    assert loaded[0].critique_rules == ["smell:bare-except"]


def test_episodic_stats(tmp_path):
    mem = EpisodicMemory(tmp_path / "ep.jsonl")
    mem.record(Episode(task="t1", accepted=True, verified=True))
    mem.record(Episode(task="t2", accepted=False, verified=False))
    stats = mem.stats()
    assert stats["episodes"] == 2
    assert stats["accepted"] == 1
    assert stats["rejected"] == 1


def test_find_similar_ranks_by_overlap(tmp_path):
    mem = EpisodicMemory(tmp_path / "ep.jsonl")
    mem.record(Episode(task="add oauth login endpoint"))
    mem.record(Episode(task="fix database connection pool"))
    hits = mem.find_similar("add oauth login flow", top_k=2)
    assert hits
    assert "oauth" in hits[0][0].task
    assert hits[0][1] > 0


# ---- lessons ---------------------------------------------------------------
def test_lessons_count_recurring_rules():
    eps = [
        Episode(task="a", critique_rules=["secret:aws-access-key"]),
        Episode(task="b", critique_rules=["secret:aws-access-key", "smell:bare-except"]),
        Episode(task="c", critique_rules=["secret:aws-access-key"]),
    ]
    lessons = LessonStore().derive(eps)
    top = lessons[0]
    assert top.pattern == "secret:aws-access-key"
    assert top.count == 3
    assert "environment" in top.advice.lower()


def test_lessons_include_verification_failures():
    eps = [Episode(task="x", verified=False), Episode(task="y", verified=False)]
    lessons = LessonStore().derive(eps)
    assert any(l.pattern == "verification-failure" for l in lessons)


# ---- conventions -----------------------------------------------------------
def test_convention_detection_python(tmp_path):
    (tmp_path / "m.py").write_text(
        'def add_two(a: int, b: int) -> int:\n'
        '    """Add two numbers."""\n'
        "    return a + b\n\n\n"
        "class WidgetFactory:\n"
        '    """Makes widgets."""\n'
        "    def build(self) -> str:\n"
        '        return "widget"\n',
        encoding="utf-8",
    )
    conv = ConventionDetector(tmp_path).detect()
    assert conv.function_naming == "snake_case"
    assert conv.class_naming == "PascalCase"
    assert conv.quote_style == "double"
    assert conv.type_hint_coverage > 0.5
    assert conv.docstring_coverage > 0.5


# ---- system façade ---------------------------------------------------------
def test_memory_system_guidance_grows(tmp_path):
    sys = MemorySystem(tmp_path)
    # nothing learned yet -> empty guidance
    assert sys.guidance_for("add a feature") == ""

    sys.learn_conventions(force=True)
    sys.record_episode(Episode(task="add api key handling",
                               critique_rules=["secret:aws-access-key"],
                               accepted=False))
    guidance = sys.guidance_for("add another api key feature")
    assert "conventions" in guidance.lower()
    assert "environment" in guidance.lower()  # the secret lesson surfaced


def test_relevant_lessons_prefers_similar_tasks(tmp_path):
    sys = MemorySystem(tmp_path)
    sys.record_episode(Episode(task="parse yaml config",
                               critique_rules=["vuln:pickle-loads"]))
    sys.record_episode(Episode(task="render html page",
                               critique_rules=["smell:bare-except"]))
    lessons = sys.relevant_lessons("parse yaml settings file", n=3)
    # the pickle lesson (from the similar yaml task) should be present
    assert any(l.pattern == "vuln:pickle-loads" for l in lessons)


# ---- resilience (memory must never break the workflow) ---------------------
def test_corrupt_conventions_cache_does_not_raise(tmp_path):
    sys = MemorySystem(tmp_path)
    sys._conventions_path.write_text("{ this is not valid json", encoding="utf-8")
    assert sys.conventions() is None          # tolerated, not raised
    assert sys.guidance_for("anything") == "" or isinstance(sys.guidance_for("x"), str)


def test_schema_drift_in_conventions_cache_is_tolerated(tmp_path):
    sys = MemorySystem(tmp_path)
    sys._conventions_path.write_text(
        '{"indent": "tabs", "unknown_future_field": 99}', encoding="utf-8")
    conv = sys.conventions()
    assert conv is not None
    assert conv.indent == "tabs"              # known field kept, extra ignored


def test_non_dict_episode_line_is_skipped(tmp_path):
    mem = EpisodicMemory(tmp_path / "ep.jsonl")
    mem.record(Episode(task="real"))
    with (tmp_path / "ep.jsonl").open("a", encoding="utf-8") as fh:
        fh.write("42\n")          # valid JSON, not an object
        fh.write('"a string"\n')
        fh.write("[1, 2, 3]\n")
    episodes = mem.all()
    assert len(episodes) == 1     # only the real episode survives
    assert episodes[0].task == "real"


def test_non_utf8_file_does_not_break_detection(tmp_path):
    (tmp_path / "good.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    (tmp_path / "bad.py").write_bytes(b"x = '\xff\xfe invalid utf8'\n")
    conv = ConventionDetector(tmp_path).detect()  # must not raise
    assert conv.function_naming == "snake_case"


def test_kwonly_and_vararg_hints_counted(tmp_path):
    (tmp_path / "m.py").write_text(
        "def f(*nums: int) -> None:\n    pass\n", encoding="utf-8")
    conv = ConventionDetector(tmp_path).detect()
    assert conv.type_hint_coverage == 1.0
