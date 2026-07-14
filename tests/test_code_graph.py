from god_agent.context.code_graph import CodeGraph

SAMPLE = '''
import os
from collections import defaultdict

def helper(x):
    """A helper."""
    return x + 1

class Service:
    def run(self, items):
        total = 0
        for item in items:
            if item > 0:
                total += helper(item)
        return total
'''


def test_indexes_symbols(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text(SAMPLE, encoding="utf-8")
    g = CodeGraph()
    g.add_file(f, tmp_path)

    assert g.find("helper")
    assert g.find("Service")
    run = g.find("run")
    assert run and run[0].kind == "method"


def test_imports_recorded(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text(SAMPLE, encoding="utf-8")
    g = CodeGraph()
    g.add_file(f, tmp_path)
    modules = {e.module for e in g.imports}
    assert "os" in modules
    assert "collections" in modules


def test_callers_and_impact(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text(SAMPLE, encoding="utf-8")
    g = CodeGraph()
    g.add_file(f, tmp_path)
    callers = g.callers_of("helper")
    assert any(c.name == "run" for c in callers)
    impact = g.impact_of("helper")
    assert any("run" in caller for caller in impact["direct_callers"])


def test_complexity_hotspots(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text(SAMPLE, encoding="utf-8")
    g = CodeGraph()
    g.add_file(f, tmp_path)
    hot = g.hotspots(top=1)
    assert hot[0].name == "run"  # has a loop + branch


def test_build_skips_bad_syntax(tmp_path):
    (tmp_path / "good.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / "bad.py").write_text("def (:\n", encoding="utf-8")
    g = CodeGraph().build(tmp_path)
    assert g.find("a")
    assert g.stats()["symbols"] >= 1
