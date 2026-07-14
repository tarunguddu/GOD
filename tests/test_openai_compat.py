import pytest

from god_agent.llm.base import LLMRequest, Message
from god_agent.llm.openai_compat import OpenAICompatibleProvider
from god_agent.llm.transport import LLMHTTPError


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, payload, timeout):
        self.calls.append({"url": url, "headers": headers, "payload": payload})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _ok(text="hello", model="gpt-4o-mini"):
    return {"choices": [{"message": {"role": "assistant", "content": text}}],
            "model": model,
            "usage": {"prompt_tokens": 5, "completion_tokens": 2}}


def _req(text="hi", system=None, model=None):
    return LLMRequest(messages=[Message("user", text)], system=system, model=model)


def test_completion_and_usage_mapping():
    t = FakeTransport([_ok()])
    p = OpenAICompatibleProvider("gpt-4o-mini", "https://api.openai.com/v1",
                                 api_key="sk-test", transport=t)
    resp = p.complete(_req())
    assert resp.text == "hello"
    assert resp.usage == {"input_tokens": 5, "output_tokens": 2}
    assert t.calls[0]["url"] == "https://api.openai.com/v1/chat/completions"
    assert t.calls[0]["headers"]["Authorization"] == "Bearer sk-test"


def test_system_message_prepended():
    t = FakeTransport([_ok()])
    p = OpenAICompatibleProvider("m", "http://x/v1", api_key="k", transport=t)
    p.complete(_req(system="be terse"))
    msgs = t.calls[0]["payload"]["messages"]
    assert msgs[0] == {"role": "system", "content": "be terse"}


def test_local_provider_needs_no_key():
    p = OpenAICompatibleProvider("llama3.2", "http://localhost:11434/v1",
                                 requires_key=False)
    assert p.available is True


def test_hosted_provider_unavailable_without_key():
    p = OpenAICompatibleProvider("gpt-4o", "https://api.openai.com/v1",
                                 api_key=None, api_key_env="DOES_NOT_EXIST_XYZ",
                                 requires_key=True)
    assert p.available is False
    with pytest.raises(RuntimeError):
        p.complete(_req())


def test_retry_on_429():
    t = FakeTransport([LLMHTTPError(429, "slow down"), _ok("ok")])
    import god_agent.llm.transport as tr
    orig, tr.time.sleep = tr.time.sleep, lambda s: None
    try:
        p = OpenAICompatibleProvider("m", "http://x/v1", api_key="k", transport=t)
        resp = p.complete(_req())
    finally:
        tr.time.sleep = orig
    assert resp.text == "ok"
    assert len(t.calls) == 2


def test_per_request_model_override():
    t = FakeTransport([_ok(model="custom")])
    p = OpenAICompatibleProvider("default", "http://x/v1", api_key="k", transport=t)
    p.complete(_req(model="custom"))
    assert t.calls[0]["payload"]["model"] == "custom"


def test_unexpected_shape_raises():
    t = FakeTransport([{"unexpected": True}])
    p = OpenAICompatibleProvider("m", "http://x/v1", api_key="k", transport=t)
    with pytest.raises(RuntimeError):
        p.complete(_req())
