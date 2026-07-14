import pytest

from god_agent.llm.base import LLMRequest, Message
from god_agent.llm.gemini_provider import GeminiProvider


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, url, headers, payload, timeout):
        self.calls.append({"url": url, "payload": payload})
        return self.response


_OK = {
    "candidates": [{"content": {"parts": [{"text": "hi there"}]}}],
    "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 2},
}


def _p(transport):
    return GeminiProvider(api_key="g-test", transport=transport)


def test_completion_parsed():
    t = FakeTransport(_OK)
    resp = _p(t).complete(LLMRequest(messages=[Message("user", "hi")]))
    assert resp.text == "hi there"
    assert resp.usage == {"input_tokens": 4, "output_tokens": 2}


def test_key_in_query_and_role_mapping():
    t = FakeTransport(_OK)
    req = LLMRequest(messages=[Message("user", "a"), Message("assistant", "b")])
    _p(t).complete(req)
    assert "key=g-test" in t.calls[0]["url"]
    roles = [c["role"] for c in t.calls[0]["payload"]["contents"]]
    assert roles == ["user", "model"]      # assistant -> model


def test_system_instruction():
    t = FakeTransport(_OK)
    req = LLMRequest(messages=[Message("user", "hi")], system="be brief")
    _p(t).complete(req)
    assert t.calls[0]["payload"]["systemInstruction"]["parts"][0]["text"] == "be brief"


def test_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    p = GeminiProvider()
    assert not p.available


def test_empty_candidates_safe():
    resp = _p(FakeTransport({"candidates": []})).complete(
        LLMRequest(messages=[Message("user", "hi")]))
    assert resp.text == ""
