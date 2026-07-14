"""LLM orchestration layer.

Provides a provider-agnostic interface so the deterministic parts of the agent
work fully offline (via :class:`MockProvider`) while a real backend
(:class:`AnthropicProvider`) can be plugged in when an API key is present.
"""

from .base import LLMProvider, LLMRequest, LLMResponse, Message
from .mock import MockProvider
from .scripted import ScriptedProvider
from .openai_compat import OpenAICompatibleProvider
from .registry import PRESETS, Preset, build_provider, list_presets
from .orchestrator import LLMOrchestrator, get_provider

__all__ = [
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "Message",
    "MockProvider",
    "ScriptedProvider",
    "OpenAICompatibleProvider",
    "PRESETS",
    "Preset",
    "build_provider",
    "list_presets",
    "LLMOrchestrator",
    "get_provider",
]
