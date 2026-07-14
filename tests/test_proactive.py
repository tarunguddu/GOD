from god_agent.agent import GodAgent
from god_agent.config import Config
from god_agent.proactive import ProactiveEngine, Suggestion, HealthReport
from god_agent.reasoning.critic import Severity


def _agent(project):
    return GodAgent(Config.load(project))


def test_clean_project_high_score(project):
    agent = _agent(project)
    agent.fs.write_file("src/clean.py", "def ok():\n    return 1\n")
    report = agent.proactive.analyze()
    assert report.score >= 80
    assert isinstance(report, HealthReport)


def test_detects_security_issue(project):
    agent = _agent(project)
    agent.fs.write_file(
        "src/danger.py",
        "import subprocess\ndef r(c):\n    subprocess.run(c, shell=True)\n",
    )
    report = agent.proactive.analyze()
    sec = [s for s in report.suggestions if s.category == "security"]
    assert sec
    assert any(s.severity >= Severity.HIGH for s in sec)
    assert report.score < 100


def test_detects_missing_tests(project):
    agent = _agent(project)
    agent.fs.write_file("src/widget.py", "def build():\n    return 1\n")
    report = agent.proactive.analyze()
    testing = [s for s in report.suggestions if s.category == "testing"]
    assert any("widget.py" in s.location for s in testing)


def test_detects_large_file(project):
    agent = _agent(project)
    big = "\n".join(f"x{i} = {i}" for i in range(450))
    agent.fs.write_file("src/big.py", big + "\n")
    report = agent.proactive.analyze()
    assert any("large file" in s.message for s in report.suggestions)


def test_score_penalises_severity():
    report = HealthReport(scanned_files=1)
    report.suggestions.append(Suggestion("security", Severity.CRITICAL, "x"))
    assert report.score == 75
    report.suggestions.append(Suggestion("security", Severity.CRITICAL, "y"))
    assert report.score == 50


def test_report_render_groups_and_sorts(project):
    agent = _agent(project)
    agent.fs.write_file("src/danger.py",
                        "def e(x):\n    return eval(x)\n")
    report = agent.proactive.analyze()
    text = report.render()
    assert "health score" in text.lower()
    # highest severity first
    ordered = report.by_severity()
    sev = [int(s.severity) for s in ordered]
    assert sev == sorted(sev, reverse=True)


def test_empty_paths_does_not_full_scan(project):
    # analyze(paths=[]) must scan nothing (not fall back to the whole tree).
    agent = _agent(project)
    agent.fs.write_file("src/danger.py", "def e(x):\n    return eval(x)\n")
    report = agent.proactive.analyze(paths=[])
    assert report.scanned_files == 0
    assert report.suggestions == []


def test_scoped_analyze_only_reports_given_files(project):
    agent = _agent(project)
    agent.fs.write_file("src/danger.py", "def e(x):\n    return eval(x)\n")
    agent.fs.write_file("src/clean.py", "def ok():\n    return 1\n")
    report = agent.proactive.analyze(paths=["src/clean.py"])
    # Only clean.py was in scope, so no security finding from danger.py.
    assert not any(s.category == "security" for s in report.suggestions)
    # testing/complexity scanners are also scoped -> no danger.py mentions
    assert all("danger.py" not in s.location for s in report.suggestions)
