"""Deterministic offline provider.

Lets the whole agent run and be tested without an API key or network. It echoes
structured, predictable output so tests are stable and so a developer can drive
the full workflow (planning, tool use, verification) before wiring a real model.
"""

from __future__ import annotations

import hashlib

from .base import LLMProvider, LLMRequest, LLMResponse


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(self, model: str = "mock-1") -> None:
        self.model = model

    def complete(self, request: LLMRequest) -> LLMResponse:
        user = request.user_text()
        digest = hashlib.sha256(user.encode("utf-8")).hexdigest()[:8]
        text = (
            "[mock-response] I cannot reason without a real model, but here is a "
            "deterministic acknowledgement so the workflow can be exercised.\n"
            f"- request_id: {digest}\n"
            f"- received_chars: {len(user)}\n"
            "- note: set llm_provider='anthropic' with an API key for real output."
        )
        return LLMResponse(
            text=text,
            model=self.model,
            provider=self.name,
            usage={"input_chars": len(user), "output_chars": len(text)},
        )
