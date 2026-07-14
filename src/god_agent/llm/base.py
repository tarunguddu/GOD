"""Provider-agnostic LLM interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Message:
    role: str   # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMRequest:
    messages: list[Message]
    max_tokens: int = 1024
    temperature: float = 0.2
    system: str | None = None
    model: str | None = None      # per-request override of the provider default

    def user_text(self) -> str:
        return "\n".join(m.content for m in self.messages if m.role == "user")


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    raw: object | None = None


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse:
        ...

    @property
    def available(self) -> bool:
        return True
