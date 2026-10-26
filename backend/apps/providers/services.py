from __future__ import annotations

from .anthropic_provider import AnthropicProvider
from .base import ChatProvider
from .gemini_provider import GeminiProvider

_PROVIDERS: dict[str, ChatProvider] = {
    "anthropic": AnthropicProvider(),
    "gemini": GeminiProvider(),
}


def get_provider(name: str) -> ChatProvider:
    return _PROVIDERS[name]


def register_provider(provider: ChatProvider) -> None:
    """Register an additional provider (used by plugins and by test fixtures)."""
    _PROVIDERS[provider.name] = provider
