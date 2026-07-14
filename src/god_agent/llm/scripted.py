"""Scripted provider — returns pre-set responses in order.

Useful for two things:
  - Deterministic tests of the generation / self-correction loop without a
    network or API key.
  - Demos / dry-runs where you want to exercise the full pipeline with canned
    model output.

Once the scripted responses are exhausted it repeats the last one (so a loop
that keeps retrying gets a stable answer rather than crashing).
"""

from __future__ import annotations

from .base import LLMProvider, LLMRequest, LLMResponse


class ScriptedProvider(LLMProvider):
    name = "scripted"

    def __init__(self, responses: list[str], model: str = "scripted-1") -> None:
        if not responses:
            raise ValueError("ScriptedProvider needs at least one response")
        self.responses = list(responses)
        self.model = model
        self.calls = 0

    def complete(self, request: LLMRequest) -> LLMResponse:
        idx = min(self.calls, len(self.responses) - 1)
        text = self.responses[idx]
        self.calls += 1
        return LLMResponse(
            text=text, model=self.model, provider=self.name,
            usage={"input_chars": len(request.user_text()), "output_chars": len(text)},
        )
