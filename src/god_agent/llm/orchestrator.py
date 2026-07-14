"""Model routing + usage accounting.

Selects a provider, tracks cumulative usage (addressing the "costs accumulate
unpredictably" reality with at least in-session visibility), and falls back to
the mock provider when a real one is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import Config
from .base import LLMProvider, LLMRequest, LLMResponse, Message
from .mock import MockProvider


def get_provider(config: Config) -> LLMProvider:
    """Resolve the configured provider via the registry, falling back to mock
    when the chosen provider isn't available (missing key, etc.)."""
    from .registry import build_provider
    return build_provider(
        provider=config.llm_provider,
        model=config.llm_model,
        base_url=getattr(config, "llm_base_url", None),
        api_key_env=config.llm_api_key_env,
        extra_headers=getattr(config, "llm_extra_headers", None) or None,
        fallback_to_mock=True,
    )


@dataclass
class UsageTotals:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    input_chars: int = 0
    output_chars: int = 0

    def add(self, usage: dict) -> None:
        self.requests += 1
        self.input_tokens += usage.get("input_tokens", 0)
        self.output_tokens += usage.get("output_tokens", 0)
        self.input_chars += usage.get("input_chars", 0)
        self.output_chars += usage.get("output_chars", 0)


class LLMOrchestrator:
    def __init__(self, provider: LLMProvider, budget_tokens: int | None = None) -> None:
        self.provider = provider
        self.usage = UsageTotals()
        self.budget_tokens = budget_tokens

    @property
    def over_budget(self) -> bool:
        if self.budget_tokens is None:
            return False
        return (self.usage.input_tokens + self.usage.output_tokens) >= self.budget_tokens

    def complete(self, prompt: str, system: str | None = None,
                 max_tokens: int = 1024, model: str | None = None) -> LLMResponse:
        if self.over_budget:
            raise RuntimeError(
                f"Token budget ({self.budget_tokens}) exhausted. Pausing for "
                f"confirmation before further LLM spend."
            )
        request = LLMRequest(
            messages=[Message("user", prompt)],
            system=system,
            max_tokens=max_tokens,
            model=model,
        )
        response = self.provider.complete(request)
        self.usage.add(response.usage)
        return response
