import pytest

from god_agent.llm.base import LLMRequest, Message
from god_agent.llm.gemini_provider import GeminiProvider
from god_agent.llm.mock import MockProvider
from god_agent.llm.openai_compat import OpenAICompatibleProvider
from god_agent.llm.registry import PRESETS, build_provider, list_presets


def test_presets_cover_major_services():
    names = set(PRESETS)
    for expected in ("openai", "groq", "gemini", "anthropic", "ollama",
                     "openrouter", "mistral", "deepseek", "lmstudio", "mock"):
        assert expected in names


def test_local_preset_builds_and_is_available_without_key():
    p = build_provider("ollama", fallback_to_mock=False)
    assert isinstance(p, OpenAICompatibleProvider)
    assert p.available           # local needs no key
    assert p.base_url == "http://localhost:11434/v1"


def test_hosted_preset_falls_back_to_mock_without_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    p = build_provider("groq")           # no key in env
    assert isinstance(p, MockProvider)


def test_hosted_preset_builds_when_key_present(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    p = build_provider("groq")
    assert isinstance(p, OpenAICompatibleProvider)
    assert p.available
    assert "groq" in p.base_url


def test_custom_endpoint_via_base_url():
    p = build_provider("custom", base_url="http://my-llm:9000/v1",
                       api_key_env=None, fallback_to_mock=False)
    assert isinstance(p, OpenAICompatibleProvider)
    assert p.base_url == "http://my-llm:9000/v1"


def test_anthropic_preset_kind(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    p = build_provider("anthropic")
    assert p.name == "anthropic"
    assert p.available


def test_gemini_preset_kind(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")
    p = build_provider("gemini")
    assert isinstance(p, GeminiProvider)
    assert p.available


def test_unknown_provider_without_url_is_mock():
    p = build_provider("nonsense-provider")
    assert isinstance(p, MockProvider)


def test_model_override_applies():
    p = build_provider("ollama", model="qwen2.5-coder", fallback_to_mock=False)
    assert p.model == "qwen2.5-coder"


def test_list_presets_returns_copy():
    a = list_presets()
    a.clear()
    assert PRESETS          # original unaffected
