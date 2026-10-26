"""Google Gemini adapter (official `google-genai` SDK)."""

from __future__ import annotations

import asyncio
import weakref
from collections.abc import AsyncIterator

import httpx
from django.conf import settings
from google import genai
from google.genai import errors, types

from .base import ChatMessage, ProviderError, StreamDone, StreamEvent, TextDelta, Usage
from .registry import get_model

_STOP_REASONS = {
    "STOP": "end",
    "MAX_TOKENS": "max_tokens",
    "SAFETY": "refusal",
    "PROHIBITED_CONTENT": "refusal",
    "BLOCKLIST": "refusal",
    "SPII": "refusal",
    "RECITATION": "refusal",
}


class GeminiProvider:
    name = "gemini"

    def __init__(self) -> None:
        # Async HTTP clients are bound to the event loop that created them, so keep one per loop.
        self._clients: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, genai.Client] = (
            weakref.WeakKeyDictionary()
        )

    def is_configured(self) -> bool:
        return bool(settings.GEMINI_API_KEY)

    @property
    def client(self) -> genai.Client:
        loop = asyncio.get_running_loop()
        if loop not in self._clients:
            self._clients[loop] = genai.Client(
                api_key=settings.GEMINI_API_KEY,
                http_options=types.HttpOptions(
                    timeout=int(settings.PROVIDER_TIMEOUT_SECONDS * 1000),
                    # Retry transient overload/server errors. 429 is not retried: on the free tier it usually
                    # means a daily quota, which retrying cannot fix.
                    retry_options=types.HttpRetryOptions(
                        attempts=3, initial_delay=1.0, max_delay=8.0, http_status_codes=[408, 500, 502, 503, 504]
                    ),
                ),
            )
        return self._clients[loop]

    async def stream(
        self, *, model_id: str, messages: list[ChatMessage], system: str, max_output_tokens: int
    ) -> AsyncIterator[StreamEvent]:
        contents = [
            types.Content(role="model" if m.role == "assistant" else "user", parts=[types.Part(text=m.content)])
            for m in messages
        ]
        spec = get_model(model_id)
        level = settings.GEMINI_THINKING_LEVEL or (spec.thinking_level if spec else None)
        if level and level.lower() == "default":
            level = None
        usage = Usage()
        finish: str | None = None
        model_version: str | None = None
        started = False
        try:
            for attempt in range(2):
                thinking = types.ThinkingConfig(thinking_level=level.upper()) if level else None
                config = types.GenerateContentConfig(
                    system_instruction=system, max_output_tokens=max_output_tokens, thinking_config=thinking
                )
                try:
                    stream = await self.client.aio.models.generate_content_stream(
                        model=model_id, contents=contents, config=config
                    )
                    async for chunk in stream:
                        for candidate in chunk.candidates or []:
                            if candidate.finish_reason:
                                reason = candidate.finish_reason
                                finish = str(reason.value if hasattr(reason, "value") else reason)
                            for part in (candidate.content.parts if candidate.content else None) or []:
                                # Skip thought summaries; only the answer text is shown to the user.
                                if part.text and not part.thought:
                                    started = True
                                    yield TextDelta(part.text)
                        if chunk.usage_metadata:
                            meta = chunk.usage_metadata
                            usage = Usage(
                                input_tokens=meta.prompt_token_count or 0,
                                # Thinking tokens are billed as output.
                                output_tokens=(meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0),
                            )
                        model_version = chunk.model_version or model_version
                    break
                except errors.ClientError as e:
                    # A model that rejects the configured thinking level: retry once with the model's default.
                    if attempt == 0 and level and not started and e.code == 400 and "thinking" in str(e).lower():
                        level = None
                        continue
                    raise
        except errors.ClientError as e:
            raise _map_client_error(e, model_id) from e
        except errors.ServerError as e:
            raise ProviderError("unavailable", "Gemini is temporarily unavailable.", self.name, e.code, True) from e
        except httpx.HTTPError as e:
            raise ProviderError("unavailable", "Could not reach Gemini.", self.name, None, True) from e

        yield StreamDone(
            usage=usage,
            stop_reason=_STOP_REASONS.get(finish or "", "other" if finish else "end"),
            raw_stop_reason=finish,
            model_id=model_version or model_id,
        )


def _map_client_error(e: errors.ClientError, model_id: str) -> ProviderError:
    code = e.code
    if code == 429:
        return ProviderError("rate_limit", "Gemini rate limit or free-tier quota reached.", "gemini", 429, True)
    if code in (401, 403):
        detail = "Gemini rejected the API key, or the Gemini API is not enabled for this Google project."
        return ProviderError("auth", detail, "gemini", code)
    if code == 404:
        return ProviderError("not_found", f"Model '{model_id}' was not found.", "gemini", 404)
    return ProviderError("bad_request", (e.message or "Gemini rejected the request.")[:300], "gemini", code)
