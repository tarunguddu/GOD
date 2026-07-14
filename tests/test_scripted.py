import pytest

from god_agent.llm.base import LLMRequest, Message
from god_agent.llm.scripted import ScriptedProvider


def _req(text="hi"):
    return LLMRequest(messages=[Message("user", text)])


def test_returns_responses_in_order():
    p = ScriptedProvider(["a", "b"])
    assert p.complete(_req()).text == "a"
    assert p.complete(_req()).text == "b"


def test_repeats_last_when_exhausted():
    p = ScriptedProvider(["only"])
    assert p.complete(_req()).text == "only"
    assert p.complete(_req()).text == "only"   # repeats, does not crash
    assert p.calls == 2


def test_requires_at_least_one_response():
    with pytest.raises(ValueError):
        ScriptedProvider([])


def test_usage_reported():
    p = ScriptedProvider(["xyz"])
    resp = p.complete(_req("hello"))
    assert resp.usage["output_chars"] == 3
    assert resp.provider == "scripted"
