from god_agent.ui.diffview import diff_stat, render_unified_diff


def test_no_changes():
    assert render_unified_diff("a\n", "a\n") == "(no changes)"


def test_plain_diff_has_add_and_remove():
    out = render_unified_diff("x = 1\n", "x = 2\n", "m.py", color=False)
    assert "-x = 1" in out
    assert "+x = 2" in out
    assert "m.py" in out


def test_colored_diff_wraps_ansi():
    out = render_unified_diff("a\n", "b\n", color=True)
    assert "\033[32m" in out   # green for additions
    assert "\033[31m" in out   # red for removals
    assert "\033[0m" in out


def test_diff_stat_counts():
    added, removed = diff_stat("a\nb\nc\n", "a\nB\nc\nd\n")
    assert added == 2          # B and d
    assert removed == 1        # b
