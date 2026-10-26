"""Provider-neutral types. Each AI provider adapter translates its SDK's stream into these events."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

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


@dataclass(frozen=True)
class ToolSpec:
    """A server-side function the model may call. `parameters` is a JSON Schema object."""

    name: str
    description: str
    parameters: dict


@dataclass(frozen=True)
class ToolActivity:
    """Progress of a tool call, streamed to the client for transparency."""

    call_id: str
    name: str
    status: Literal["running", "done", "error"]
    args: dict = field(default_factory=dict)
    summary: str = ""
    artifact: dict | None = None  # e.g. a result table or chart for the UI


# Runs a tool server-side. Returns (result for the model, ToolActivity for the client).
ToolExecutor = Callable[[str, str, dict], Awaitable[tuple[dict[str, Any], ToolActivity]]]

# Upper bound on model↔tool round trips in one reply (cost and runaway-loop protection).
MAX_TOOL_ROUNDS = 6

StreamEvent = TextDelta | ToolActivity | StreamDone


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
        tools: list[ToolSpec] | None = None,
        execute: ToolExecutor | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Yield TextDelta/ToolActivity events, then exactly one StreamDone. Raise ProviderError on failure.

        When `tools` are given, the adapter runs the tool loop itself (provider message formats, such as
        Gemini thought signatures or Claude thinking blocks, must be replayed exactly), calling `execute` for
        each tool call, for at most MAX_TOOL_ROUNDS rounds. Usage is summed across rounds."""
        ...
