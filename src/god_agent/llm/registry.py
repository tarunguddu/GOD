"""Provider registry — presets for every major LLM service, hosted and local.

A *preset* is a friendly name (``"groq"``, ``"ollama"``, ``"openai"``, …) that
maps to a provider kind, a default base URL, the env var its key lives in, and a
sensible default model. Users select one with ``llm_provider = "<name>"`` and
override any field (model, base_url, key env) in config.

Adding a new OpenAI-compatible service is a one-line preset.
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import LLMProvider
from .mock import MockProvider


@dataclass(frozen=True)
class Preset:
    kind: str                 # "openai_compat" | "anthropic" | "gemini" | "mock"
    base_url: str | None
    api_key_env: str | None   # None => no key required (e.g. local)
    default_model: str
    free: bool = False        # has a usable free tier / is local
    note: str = ""


# The OpenAI-compatible kind covers the long tail; native kinds for the two
# services with their own schema.
PRESETS: dict[str, Preset] = {
    # --- hosted, OpenAI-compatible ---
    "openai": Preset("openai_compat", "https://api.openai.com/v1",
                     "OPENAI_API_KEY", "gpt-4o-mini"),
    "groq": Preset("openai_compat", "https://api.groq.com/openai/v1",
                   "GROQ_API_KEY", "llama-3.3-70b-versatile", free=True,
                   note="generous free tier, very fast"),
    "openrouter": Preset("openai_compat", "https://openrouter.ai/api/v1",
                         "OPENROUTER_API_KEY", "openai/gpt-4o-mini", free=True,
                         note="gateway to 200+ models incl. free ones"),
    "deepseek": Preset("openai_compat", "https://api.deepseek.com/v1",
                       "DEEPSEEK_API_KEY", "deepseek-chat"),
    "mistral": Preset("openai_compat", "https://api.mistral.ai/v1",
                      "MISTRAL_API_KEY", "mistral-small-latest", free=True),
    "together": Preset("openai_compat", "https://api.together.xyz/v1",
                       "TOGETHER_API_KEY", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    "fireworks": Preset("openai_compat", "https://api.fireworks.ai/inference/v1",
                        "FIREWORKS_API_KEY", "accounts/fireworks/models/llama-v3p3-70b-instruct"),
    "xai": Preset("openai_compat", "https://api.x.ai/v1",
                  "XAI_API_KEY", "grok-2-latest"),
    "perplexity": Preset("openai_compat", "https://api.perplexity.ai",
                         "PERPLEXITY_API_KEY", "sonar"),
    # --- native schemas ---
    "anthropic": Preset("anthropic", "https://api.anthropic.com/v1",
                        "ANTHROPIC_API_KEY", "claude-sonnet-4"),
    "gemini": Preset("gemini", "https://generativelanguage.googleapis.com/v1beta",
                     "GEMINI_API_KEY", "gemini-1.5-flash", free=True,
                     note="generous free tier"),
    # --- local (no key, fully offline) ---
    "ollama": Preset("openai_compat", "http://localhost:11434/v1",
                     None, "llama3.2", free=True, note="local, no key"),
    "lmstudio": Preset("openai_compat", "http://localhost:1234/v1",
                       None, "local-model", free=True, note="local, no key"),
    "vllm": Preset("openai_compat", "http://localhost:8000/v1",
                   None, "local-model", free=True, note="local, no key"),
    "llamacpp": Preset("openai_compat", "http://localhost:8080/v1",
                       None, "local-model", free=True, note="local, no key"),
    # --- offline default ---
    "mock": Preset("mock", None, None, "mock-1", free=True,
                   note="deterministic offline stub (default)"),
}


def build_provider(
    provider: str,
    model: str | None = None,
    base_url: str | None = None,
    api_key_env: str | None = None,
    extra_headers: dict | None = None,
    fallback_to_mock: bool = True,
) -> LLMProvider:
    """Build a provider from a preset name (or a custom OpenAI-compatible URL).

    ``provider`` may be a preset name, or "custom"/"openai_compat" to use an
    explicit ``base_url``. Unknown names with a ``base_url`` are treated as
    custom OpenAI-compatible endpoints.
    """
    preset = PRESETS.get(provider)
    if preset is None:
        if base_url:                       # treat as a custom OpenAI-compatible endpoint
            preset = Preset("openai_compat", base_url, api_key_env, model or "model")
        else:
            preset = PRESETS["mock"]

    kind = preset.kind
    resolved_model = model or preset.default_model
    resolved_url = base_url or preset.base_url
    resolved_key_env = api_key_env or preset.api_key_env

    built: LLMProvider
    if kind == "mock":
        built = MockProvider(model=resolved_model)
    elif kind == "anthropic":
        from .anthropic_provider import AnthropicProvider
        built = AnthropicProvider(model=resolved_model, base_url=resolved_url,
                                  api_key_env=resolved_key_env or "ANTHROPIC_API_KEY")
    elif kind == "gemini":
        from .gemini_provider import GeminiProvider
        built = GeminiProvider(model=resolved_model, base_url=resolved_url,
                               api_key_env=resolved_key_env or "GEMINI_API_KEY")
    else:  # openai_compat (the common case)
        from .openai_compat import OpenAICompatibleProvider
        built = OpenAICompatibleProvider(
            model=resolved_model, base_url=resolved_url or "http://localhost:11434/v1",
            api_key_env=resolved_key_env, extra_headers=extra_headers,
            requires_key=resolved_key_env is not None,
            label=provider if provider in PRESETS else "openai_compat",
        )

    if fallback_to_mock and not built.available:
        return MockProvider(model=resolved_model)
    return built


def list_presets() -> dict[str, Preset]:
    return dict(PRESETS)
