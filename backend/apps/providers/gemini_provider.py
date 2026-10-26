"""Google Gemini adapter (official `google-genai` SDK)."""

from __future__ import annotations

import asyncio
import uuid
import weakref
from collections.abc import AsyncIterator

import httpx
from django.conf import settings
from google import genai
from google.genai import errors, types

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
        self,
        *,
        model_id: str,
        messages: list[ChatMessage],
        system: str,
        max_output_tokens: int,
        tools: list[ToolSpec] | None = None,
        execute: ToolExecutor | None = None,
    ) -> AsyncIterator[StreamEvent]:
        contents: list[types.Content] = [
            types.Content(role="model" if m.role == "assistant" else "user", parts=[types.Part(text=m.content)])
            for m in messages
        ]
        spec = get_model(model_id)
        level = settings.GEMINI_THINKING_LEVEL or (spec.thinking_level if spec else None)
        if level and level.lower() == "default":
            level = None
        declared = None
        if tools and execute:
            declared = [
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(name=t.name, description=t.description,
                                                  parameters_json_schema=t.parameters)
                        for t in tools
                    ]
                )
            ]

        input_tokens = output_tokens = 0
        finish: str | None = None
        model_version: str | None = None
        try:
            for round_number in range(MAX_TOOL_ROUNDS + 1):
                # The final round offers no tools, forcing a text answer instead of an endless tool loop.
                offered = declared if round_number < MAX_TOOL_ROUNDS else None
                parts: list[types.Part] = []
                round_in = round_out = 0
                for attempt in range(2):
                    config = types.GenerateContentConfig(
                        system_instruction=system,
                        max_output_tokens=max_output_tokens,
                        thinking_config=types.ThinkingConfig(thinking_level=level.upper()) if level else None,
                        tools=offered,
                        automatic_function_calling=(
                            types.AutomaticFunctionCallingConfig(disable=True) if offered else None
                        ),
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
                                    parts.append(part)  # kept verbatim: thought signatures must be replayed
                                    # Skip thought summaries; only the answer text is shown to the user.
                                    if part.text and not part.thought:
                                        yield TextDelta(part.text)
                            if chunk.usage_metadata:
                                meta = chunk.usage_metadata
                                round_in = meta.prompt_token_count or 0
                                # Thinking tokens are billed as output.
                                round_out = (meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0)
                            model_version = chunk.model_version or model_version
                        break
                    except errors.ClientError as e:
                        # A model that rejects the configured thinking level: retry once with the model default.
                        if attempt == 0 and level and not parts and e.code == 400 and "thinking" in str(e).lower():
                            level = None
                            continue
                        raise
                input_tokens += round_in
                output_tokens += round_out

                calls = [p.function_call for p in parts if p.function_call]
                if not calls or not offered:
                    break
                contents.append(types.Content(role="model", parts=parts))
                responses: list[types.Part] = []
                for call in calls:
                    call_id = call.id or uuid.uuid4().hex[:12]
                    name, args = call.name or "", dict(call.args or {})
                    yield ToolActivity(call_id, name, "running", args)
                    result, activity = await execute(call_id, name, args)
                    yield activity
                    responses.append(
                        types.Part(function_response=types.FunctionResponse(id=call.id, name=name, response=result))
                    )
                contents.append(types.Content(role="user", parts=responses))
        except errors.ClientError as e:
            raise _map_client_error(e, model_id) from e
        except errors.ServerError as e:
            raise ProviderError("unavailable", "Gemini is temporarily unavailable.", self.name, e.code, True) from e
        except httpx.HTTPError as e:
            raise ProviderError("unavailable", "Could not reach Gemini.", self.name, None, True) from e

        yield StreamDone(
            usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
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
