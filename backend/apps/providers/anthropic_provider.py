"""Anthropic Claude adapter (official `anthropic` SDK)."""

from __future__ import annotations

import asyncio
import weakref
from collections.abc import AsyncIterator

import anthropic
from django.conf import settings

from .base import ChatMessage, ProviderError, StreamDone, StreamEvent, TextDelta, Usage
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
        self, *, model_id: str, messages: list[ChatMessage], system: str, max_output_tokens: int
    ) -> AsyncIterator[StreamEvent]:
        spec = get_model(model_id)
        extra: dict = {}
        if spec and spec.supports_fallbacks:
            # Server-side fallback: if a safety classifier declines, Anthropic retries on a suitable model.
            extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        try:
            async with self.client.beta.messages.stream(
                model=model_id,
                max_tokens=max_output_tokens,
                system=system,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                thinking={"type": "adaptive"},
                **extra,
            ) as stream:
                async for event in stream:
                    if event.type == "text":
                        yield TextDelta(event.text)
                final = await stream.get_final_message()
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

        usage = final.usage
        yield StreamDone(
            usage=Usage(
                input_tokens=(usage.input_tokens or 0)
                + (usage.cache_read_input_tokens or 0)
                + (usage.cache_creation_input_tokens or 0),
                output_tokens=usage.output_tokens or 0,
            ),
            stop_reason=_STOP_REASONS.get(final.stop_reason or "", "other"),
            raw_stop_reason=final.stop_reason,
            model_id=final.model,
        )


def _safe_message(error: anthropic.APIStatusError) -> str:
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        msg = (body.get("error") or {}).get("message")
        if msg:
            return str(msg)[:300]
    return "The request was rejected by Anthropic."
