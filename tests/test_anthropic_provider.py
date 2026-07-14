import os

import pytest

from god_agent.llm.anthropic_provider import AnthropicProvider
from god_agent.llm.base import LLMRequest, Message
from god_agent.llm.transport import LLMHTTPError


def _req(text="hi", model=None):
    return LLMRequest(messages=[Message("user", text)], model=model)


class FakeTransport:
    """Records calls and returns canned responses (or raises) per call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, payload, timeout):
        self.calls.append({"url": url, "headers": headers, "payload": payload})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


_OK = {"content": [{"type": "text", "text": "pong"}],
       "model": "claude-sonnet-4",
       "usage": {"input_tokens": 3, "output_tokens": 1}}


def _provider(transport, **kw):
    return AnthropicProvider(api_key="test-key", transport=transport, **kw)


def test_basic_completion_parsed():
    t = FakeTransport([_OK])
    resp = _provider(t).complete(_req())
    assert resp.text == "pong"
    assert resp.usage == {"input_tokens": 3, "output_tokens": 1}
    # sends to the messages endpoint with the version header
    assert t.calls[0]["url"].endswith("/messages")
    assert t.calls[0]["headers"]["anthropic-version"]


def test_system_prompt_threaded():
    t = FakeTransport([_OK])
    req = LLMRequest(messages=[Message("user", "hi")], system="be terse")
    _provider(t).complete(req)
    assert t.calls[0]["payload"]["system"] == "be terse"


def test_per_request_model_override():
    t = FakeTransport([_OK])
    _provider(t, model="default").complete(_req(model="override-model"))
    assert t.calls[0]["payload"]["model"] == "override-model"


def test_retries_transient_then_succeeds():
    t = FakeTransport([LLMHTTPError(429, "rate limited"), _OK])
    import god_agent.llm.transport as tr
    orig, tr.time.sleep = tr.time.sleep, lambda s: None
    try:
        resp = _provider(t).complete(_req())
    finally:
        tr.time.sleep = orig
    assert resp.text == "pong"
    assert len(t.calls) == 2


def test_non_transient_raises_immediately():
    t = FakeTransport([LLMHTTPError(401, "unauthorized")])
    with pytest.raises(LLMHTTPError):
        _provider(t).complete(_req())
    assert len(t.calls) == 1


def test_unavailable_without_key():
    p = AnthropicProvider(api_key=None)
    p.api_key = None
    assert not p.available
    with pytest.raises(RuntimeError):
        p.complete(_req())


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"),
                    reason="no ANTHROPIC_API_KEY set — skipping live round-trip")
def test_live_roundtrip():
    resp = AnthropicProvider().complete(
        LLMRequest(messages=[Message("user", "reply with the word pong")]))
    assert resp.text
