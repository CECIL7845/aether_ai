"""Anthropic Claude adapter (official `anthropic` SDK)."""

from __future__ import annotations

import asyncio
import json
import weakref
from collections.abc import AsyncIterator

import anthropic
from django.conf import settings

from .base import (
    MAX_TOOL_ROUNDS,
    ChatMessage,
    ProviderError,
    StreamDone,
    StreamEvent,
    TextDelta,
    ToolActivity,
    ToolExecutor,
    ToolSpec,
    Usage,
)
from .registry import get_model

_STOP_REASONS = {"end_turn": "end", "stop_sequence": "end", "max_tokens": "max_tokens", "refusal": "refusal"}


class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        # Async HTTP clients are bound to the event loop that created them, so keep one per loop.
        self._clients: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, anthropic.AsyncAnthropic] = (
            weakref.WeakKeyDictionary()
        )

    def is_configured(self) -> bool:
        return bool(settings.ANTHROPIC_API_KEY)

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        loop = asyncio.get_running_loop()
        if loop not in self._clients:
            self._clients[loop] = anthropic.AsyncAnthropic(
                api_key=settings.ANTHROPIC_API_KEY, timeout=settings.PROVIDER_TIMEOUT_SECONDS, max_retries=2
            )
        return self._clients[loop]

    async def stream(
        self,
        *,
        model_id: str,
        messages: list[ChatMessage],
        system: str,
        max_output_tokens: int,
        tools: list[ToolSpec] | None = None,
        execute: ToolExecutor | None = None,
    ) -> AsyncIterator[StreamEvent]:
        spec = get_model(model_id)
        extra: dict = {}
        if spec and spec.supports_fallbacks:
            # Server-side fallback: if a safety classifier declines, Anthropic retries on a suitable model.
            extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        tool_defs = [
            # eager_input_streaming streams large tool inputs as generated; inputs are validated by the executor.
            {"name": t.name, "description": t.description, "input_schema": t.parameters, "eager_input_streaming": True}
            for t in (tools or [])
        ] if execute else []
        history: list[dict] = [{"role": m.role, "content": m.content} for m in messages]
        input_tokens = output_tokens = 0
        final = None
        try:
            for round_number in range(MAX_TOOL_ROUNDS + 1):
                offered = tool_defs if round_number < MAX_TOOL_ROUNDS else []
                async with self.client.beta.messages.stream(
                    model=model_id,
                    max_tokens=max_output_tokens,
                    system=system,
                    messages=history,
                    thinking={"type": "adaptive"},
                    **({"tools": offered} if offered else {}),
                    **extra,
                ) as stream:
                    async for event in stream:
                        if event.type == "text":
                            yield TextDelta(event.text)
                    final = await stream.get_final_message()
                usage = final.usage
                input_tokens += (
                    (usage.input_tokens or 0)
                    + (usage.cache_read_input_tokens or 0)
                    + (usage.cache_creation_input_tokens or 0)
                )
                output_tokens += usage.output_tokens or 0

                tool_uses = [b for b in final.content if b.type == "tool_use"]
                # Only run tools for a complete tool turn: a refusal or a max_tokens cut can leave a truncated input.
                if not offered or not tool_uses or final.stop_reason != "tool_use":
                    break
                # Replay Claude's full content (including thinking blocks) unchanged, then the tool results.
                history.append({"role": "assistant", "content": final.content})
                results = []
                for block in tool_uses:
                    args = block.input if isinstance(block.input, dict) else {}
                    yield ToolActivity(block.id, block.name, "running", args)
                    result, activity = await execute(block.id, block.name, args)
                    yield activity
                    results.append({
                        "type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result, default=str),
                        **({"is_error": True} if activity.status == "error" else {}),
                    })
                history.append({"role": "user", "content": results})
        except anthropic.AuthenticationError as e:
            raise ProviderError("auth", "Anthropic rejected the API key.", self.name, 401) from e
        except anthropic.PermissionDeniedError as e:
            raise ProviderError("auth", "The Anthropic API key lacks permission.", self.name, 403) from e
        except anthropic.NotFoundError as e:
            raise ProviderError("not_found", f"Model '{model_id}' was not found.", self.name, 404) from e
        except anthropic.RateLimitError as e:
            raise ProviderError("rate_limit", "Anthropic rate limit reached.", self.name, 429, True) from e
        except anthropic.BadRequestError as e:
            raise ProviderError("bad_request", _safe_message(e), self.name, 400) from e
        except anthropic.APIStatusError as e:
            raise ProviderError("unavailable", "Anthropic is temporarily unavailable.", self.name,
                                e.status_code, True) from e
        except anthropic.APIConnectionError as e:
            raise ProviderError("unavailable", "Could not reach Anthropic.", self.name, None, True) from e
        except ValueError as e:
            # The SDK raises ValueError for tool-input JSON it cannot parse at all.
            raise ProviderError("bad_request", "The model produced an unreadable tool call.", self.name) from e

        yield StreamDone(
            usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
            stop_reason=_STOP_REASONS.get(final.stop_reason or "", "other") if final else "other",
            raw_stop_reason=final.stop_reason if final else None,
            model_id=final.model if final else model_id,
        )


def _safe_message(error: anthropic.APIStatusError) -> str:
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        msg = (body.get("error") or {}).get("message")
        if msg:
            return str(msg)[:300]
    return "The request was rejected by Anthropic."
