"""Google Gemini provider (native generateContent API, dependency-free).

Gemini has a generous free tier, which makes it a great default for trying the
agent's generation features at no cost. Set the key in ``GEMINI_API_KEY``.
"""

from __future__ import annotations

import os

from .base import LLMProvider, LLMRequest, LLMResponse
from .transport import Transport, post_json, with_retry


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(
        self,
        model: str = "gemini-1.5-flash",
        api_key_env: str = "GEMINI_API_KEY",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        api_key: str | None = None,
        max_retries: int = 3,
        timeout: float = 120.0,
        transport: Transport | None = None,
    ) -> None:
        self.model = model
        self.api_key_env = api_key_env
        self.api_key = api_key or os.environ.get(api_key_env) or os.environ.get("GOOGLE_API_KEY")
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
                f"GeminiProvider unavailable: set ${self.api_key_env}.")
        model = request.model or self.model
        system = request.system or next(
            (m.content for m in request.messages if m.role == "system"), None)
        # Gemini uses roles "user" and "model" (not "assistant").
        contents = [
            {"role": "model" if m.role == "assistant" else "user",
             "parts": [{"text": m.content}]}
            for m in request.messages if m.role != "system"
        ]
        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": request.max_tokens,
                "temperature": request.temperature,
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        # Key is passed as a query parameter for the generateContent endpoint.
        url = f"{self.base_url}/models/{model}:generateContent?key={self.api_key}"
        data = with_retry(
            lambda: self._post(url, {}, payload, self.timeout),
            max_retries=self.max_retries,
        )
        text = self._extract_text(data)
        usage_raw = data.get("usageMetadata") or {}
        usage = {
            "input_tokens": usage_raw.get("promptTokenCount", 0),
            "output_tokens": usage_raw.get("candidatesTokenCount", 0),
        }
        return LLMResponse(text=text, model=model, provider=self.name,
                           usage=usage, raw=data)

    @staticmethod
    def _extract_text(data: dict) -> str:
        candidates = data.get("candidates") or []
        if not candidates:
            return ""
        parts = (candidates[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts if isinstance(p, dict))
