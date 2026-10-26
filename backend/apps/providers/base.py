"""Provider-neutral types. Each AI provider adapter translates its SDK's stream into these events."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal, Protocol

Role = Literal["user", "assistant"]
ErrorKind = Literal["auth", "rate_limit", "unavailable", "bad_request", "not_found", "unknown"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class StreamDone:
    usage: Usage
    # Normalised: "end", "max_tokens", "refusal", or "other". `raw_stop_reason` keeps the provider's value.
    stop_reason: str
    raw_stop_reason: str | None = None
    # The model that actually answered (may differ from the requested one, e.g. server-side fallbacks).
    model_id: str | None = None


StreamEvent = TextDelta | StreamDone


@dataclass
class ProviderError(Exception):
    kind: ErrorKind
    message: str
    provider: str = ""
    status_code: int | None = None
    retryable: bool = field(default=False)

    def __str__(self) -> str:
        return f"{self.provider}:{self.kind}: {self.message}"


class ChatProvider(Protocol):
    name: str

    def is_configured(self) -> bool: ...

    def stream(
        self,
        *,
        model_id: str,
        messages: list[ChatMessage],
        system: str,
        max_output_tokens: int,
    ) -> AsyncIterator[StreamEvent]:
        """Yield TextDelta events, then exactly one StreamDone. Raise ProviderError on failure."""
        ...
