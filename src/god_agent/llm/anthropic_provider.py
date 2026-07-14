"""Anthropic Claude provider (native Messages API, dependency-free).

Talks to the Anthropic Messages API over stdlib HTTP — no SDK required. Set the
API key in ``ANTHROPIC_API_KEY`` (or your configured env var). Transient
failures (429/5xx/network) are retried with backoff.
"""

from __future__ import annotations

import os

from .base import LLMProvider, LLMRequest, LLMResponse
from .transport import Transport, post_json, with_retry

_ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(
        self,
        model: str = "claude-sonnet-4",
        api_key_env: str = "ANTHROPIC_API_KEY",
        base_url: str = "https://api.anthropic.com/v1",
        api_key: str | None = None,
        max_retries: int = 3,
        timeout: float = 120.0,
        transport: Transport | None = None,
    ) -> None:
        self.model = model
        self.api_key_env = api_key_env
        self.api_key = api_key or os.environ.get(api_key_env)
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.timeout = timeout
        self._post = transport or post_json

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.available:
            raise RuntimeError(
                f"AnthropicProvider unavailable: set ${self.api_key_env}.")
        model = request.model or self.model
        system = request.system or next(
            (m.content for m in request.messages if m.role == "system"), None)
        payload = {
            "model": model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": [{"role": m.role, "content": m.content}
                         for m in request.messages if m.role != "system"],
        }
        if system:
            payload["system"] = system
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
        }
        data = with_retry(
            lambda: self._post(f"{self.base_url}/messages", headers, payload, self.timeout),
            max_retries=self.max_retries,
        )
        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if isinstance(block, dict)
        )
        usage_raw = data.get("usage") or {}
        usage = {
            "input_tokens": usage_raw.get("input_tokens", 0),
            "output_tokens": usage_raw.get("output_tokens", 0),
        }
        return LLMResponse(text=text, model=data.get("model", model),
                           provider=self.name, usage=usage, raw=data)
