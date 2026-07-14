import json

from god_agent.cli import main


def test_critique_json_contract(project, capsys):
    # The VS Code extension depends on this JSON shape.
    (project / "src" / "bad.py").write_text(
        "def e(x):\n    return eval(x)\n", encoding="utf-8")
    code = main(["--root", str(project), "critique", "src/bad.py", "--json"])
    out = capsys.readouterr().out.strip().splitlines()[-1]
    data = json.loads(out)
    assert data["blocking"] is True
    assert any(f["rule"] == "vuln:dynamic-exec" for f in data["findings"])
    assert code == 1


def test_route_command(project, capsys):
    code = main(["--root", str(project), "route", "explain the architecture"])
    out = capsys.readouterr().out
    assert "tier=fast" in out
    assert code == 0


def test_status_command(project, capsys):
    code = main(["--root", str(project), "status"])
    out = capsys.readouterr().out
    assert "GOD agent" in out
    assert code == 0


def test_health_command(project, capsys):
    (project / "src" / "danger.py").write_text(
        "import subprocess\nsubprocess.run(c, shell=True)\n", encoding="utf-8")
    code = main(["--root", str(project), "health"])
    out = capsys.readouterr().out
    assert "health score" in out.lower()
    assert code == 1            # serious security finding -> non-zero gate


def test_init_scaffolds_config(project, capsys):
    code = main(["--root", str(project), "init"])
    out = capsys.readouterr().out
    assert (project / "god_agent.toml").exists()
    assert "initialized" in out.lower()
    assert code == 0


def test_memory_command_after_learn(project, capsys):
    main(["--root", str(project), "learn"])
    capsys.readouterr()
    code = main(["--root", str(project), "memory"])
    out = capsys.readouterr().out
    assert "conventions" in out.lower()
    assert code == 0


def test_onboard_command(project, capsys):
    (project / "src" / "w.py").write_text("class W:\n    pass\n", encoding="utf-8")
    code = main(["--root", str(project), "onboard"])
    out = capsys.readouterr().out
    assert "# Onboarding" in out
    assert code == 0
