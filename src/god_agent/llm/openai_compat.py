"""OpenAI-compatible provider — one adapter for most of the LLM ecosystem.

Speaks the ``/chat/completions`` schema used by OpenAI, Groq, OpenRouter,
Mistral, DeepSeek, Together, Fireworks, xAI, Perplexity, and local runners
(Ollama, LM Studio, vLLM, llama.cpp). Point ``base_url`` at the service, set the
key (or none, for local), and it works — no SDK required.
"""

from __future__ import annotations

import os

from .base import LLMProvider, LLMRequest, LLMResponse
from .transport import Transport, post_json, with_retry


class OpenAICompatibleProvider(LLMProvider):
    name = "openai_compat"

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str | None = None,
        api_key_env: str | None = None,
        extra_headers: dict | None = None,
        requires_key: bool = True,
        max_retries: int = 3,
        timeout: float = 120.0,
        transport: Transport | None = None,
        label: str | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or (os.environ.get(api_key_env) if api_key_env else None)
        self.api_key_env = api_key_env
        self.extra_headers = dict(extra_headers or {})
        self.requires_key = requires_key
        self.max_retries = max_retries
        self.timeout = timeout
        self._post = transport or post_json
        if label:
            self.name = label

    @property
    def available(self) -> bool:
        # Local endpoints (Ollama/LM Studio) need no key.
        return (not self.requires_key) or bool(self.api_key)

    def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.available:
            raise RuntimeError(
                f"Provider '{self.name}' unavailable: set the API key in "
                f"${self.api_key_env or 'API_KEY'}."
            )
        model = request.model or self.model
        url = f"{self.base_url}/chat/completions"
        headers = dict(self.extra_headers)
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": model,
            "messages": self._build_messages(request),
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        data = with_retry(
            lambda: self._post(url, headers, payload, self.timeout),
            max_retries=self.max_retries,
        )
        text, usage = self._parse(data)
        return LLMResponse(text=text, model=data.get("model", model),
                           provider=self.name, usage=usage, raw=data)

    @staticmethod
    def _build_messages(request: LLMRequest) -> list[dict]:
        messages: list[dict] = []
        system = request.system or next(
            (m.content for m in request.messages if m.role == "system"), None)
        if system:
            messages.append({"role": "system", "content": system})
        messages.extend(
            {"role": m.role, "content": m.content}
            for m in request.messages if m.role != "system"
        )
        return messages

    @staticmethod
    def _parse(data: dict) -> tuple[str, dict]:
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"unexpected response shape: {data!r}") from exc
        usage_raw = data.get("usage") or {}
        usage = {
            "input_tokens": usage_raw.get("prompt_tokens", 0),
            "output_tokens": usage_raw.get("completion_tokens", 0),
        }
        return text, usage
