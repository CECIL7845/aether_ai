"""Reply generation: builds the prompt from history, streams the provider, persists the result, records usage."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from datetime import date

from django.conf import settings
from django.core.cache import cache

from apps.providers.base import ChatMessage, ProviderError, StreamDone, TextDelta
from apps.providers.registry import ModelSpec
from apps.providers.services import get_provider
from apps.usage.models import UsageRecord
from apps.usage.services import check_quota

from .grounding import check_citations, ground, instructions
from .models import Conversation, Message

logger = logging.getLogger(__name__)

DEFAULT_TITLE = "New conversation"


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def approx_tokens(text: str) -> int:
    # Rough heuristic (≈4 characters per token) used for context trimming and for estimating stopped streams.
    return max(1, len(text) // 4)


def system_prompt() -> str:
    return (
        f"You are {settings.PRODUCT_NAME}, an AI assistant. Today's date is {date.today().isoformat()}.\n"
        "Be accurate and direct. If you are unsure or lack information, say so instead of guessing.\n"
        "You cannot browse the web, open files, or take actions yourself. Source material is provided to you only "
        "when the user enables web search or attaches documents; never claim to have looked something up otherwise.\n"
        "Format answers in Markdown. Put code in fenced code blocks with a language tag."
    )


async def build_history(conversation: Conversation, budget_tokens: int) -> list[ChatMessage]:
    """Most recent turns that fit in the budget, oldest first, always starting with a user turn."""
    rows = [
        m
        async for m in conversation.messages.filter(
            status__in=[Message.Status.COMPLETE, Message.Status.STOPPED]
        ).order_by("-created_at", "-id")
    ]
    picked: list[Message] = []
    used = 0
    for m in rows:
        if not m.content:
            continue
        cost = approx_tokens(m.content)
        if picked and used + cost > budget_tokens:
            break
        picked.append(m)
        used += cost
    picked.reverse()
    while picked and picked[0].role != Message.Role.USER:
        picked.pop(0)
    # Providers require alternating roles; merge consecutive same-role turns (e.g. after a failed reply).
    merged: list[ChatMessage] = []
    for m in picked:
        if merged and merged[-1].role == m.role:
            merged[-1] = ChatMessage(m.role, merged[-1].content + "\n\n" + m.content)
        else:
            merged.append(ChatMessage(m.role, m.content))
    return merged


async def check_rate(user_id: int) -> bool:
    key = f"gen-rate:{user_id}"
    if await cache.aadd(key, 1, timeout=60):
        return True
    try:
        count = await cache.aincr(key)
    except ValueError:  # expired between add and incr
        await cache.aset(key, 1, timeout=60)
        return True
    return count <= settings.USER_GENERATIONS_PER_MINUTE


async def generate_reply(
    user, conversation: Conversation, spec: ModelSpec, *, web: bool = False
) -> AsyncIterator[str]:
    """Stream SSE events for one assistant reply. Always ends with a `done` or `error` event."""
    started = time.monotonic()

    def ms() -> int:
        return int((time.monotonic() - started) * 1000)

    quota = await check_quota(user)
    if not quota.allowed:
        yield sse("error", {"kind": "quota", "message": quota.reason})
        return

    lock_key = f"gen-lock:{user.pk}"
    if not await cache.aadd(lock_key, 1, timeout=settings.PROVIDER_TIMEOUT_SECONDS + 30):
        yield sse("error", {"kind": "busy", "message": "A reply is already being generated. Stop it or wait."})
        return

    history = await build_history(conversation, settings.MAX_CONTEXT_TOKENS)
    assistant = await Message.objects.acreate(
        conversation=conversation, role=Message.Role.ASSISTANT, status=Message.Status.STREAMING, model_id=spec.id
    )
    parts: list[str] = []
    sources: list = []
    try:
        # Tell the client immediately, then report each slow stage so the wait is never silent.
        yield sse("start", {"assistant_message_id": assistant.pk, "model_id": spec.id})
        if web:
            yield sse("status", {"stage": "searching_web"})
        elif await conversation.documents.aexists():
            yield sse("status", {"stage": "reading_documents"})
        history, sources, grounding = await ground(user, conversation, history, web=web)
        if grounding:
            yield sse("sources", grounding)
        if not history:
            raise ProviderError("bad_request", "There is no user message to reply to.", spec.provider)
        system = system_prompt() + instructions(grounding)

        yield sse("status", {"stage": "generating", "provider": spec.provider})
        prep_ms = ms()
        provider = get_provider(spec.provider)
        max_out = min(settings.MAX_OUTPUT_TOKENS, spec.max_output_tokens)
        async for event in provider.stream(
            model_id=spec.id, messages=history, system=system, max_output_tokens=max_out
        ):
            if isinstance(event, TextDelta):
                if assistant.first_token_ms is None:
                    assistant.first_token_ms = ms()
                parts.append(event.text)
                yield sse("delta", {"text": event.text})
            elif isinstance(event, StreamDone):
                assistant.duration_ms = ms()
                assistant.citations, assistant.invalid_citations = check_citations("".join(parts), sources)
                await _finish(user, conversation, assistant, spec, "".join(parts), event)
                logger.info(
                    "reply timing model=%s prep_ms=%s first_token_ms=%s total_ms=%s web=%s",
                    assistant.model_id, prep_ms, assistant.first_token_ms, assistant.duration_ms, web,
                )
                yield sse("done", _message_summary(assistant))
    except ProviderError as e:
        logger.warning("provider error: %s (status=%s)", e, e.status_code)
        assistant.content = "".join(parts)
        assistant.status = Message.Status.ERROR
        assistant.error_kind = e.kind
        assistant.error_message = e.message[:500]
        await assistant.asave()
        yield sse("error", {"kind": e.kind, "message": e.message, "retryable": e.retryable,
                            "assistant_message_id": assistant.pk})
    except (asyncio.CancelledError, GeneratorExit):
        # Client disconnected (user pressed Stop), so the server cancels or closes this generator.
        # Keep the partial answer and charge an estimate, so stopping early can't bypass quotas.
        await _record_stopped(user, conversation, assistant, spec, history, "".join(parts))
        raise
    except Exception:
        logger.exception("unexpected error while generating reply")
        assistant.content = "".join(parts)
        assistant.status = Message.Status.ERROR
        assistant.error_kind = "unknown"
        assistant.error_message = "Something went wrong while generating the reply."
        await assistant.asave()
        yield sse("error", {"kind": "unknown", "message": assistant.error_message,
                            "assistant_message_id": assistant.pk})
    finally:
        await cache.adelete(lock_key)


async def _finish(user, conversation, assistant, spec, text, done: StreamDone) -> None:
    cost = spec.estimate_cost(done.usage.input_tokens, done.usage.output_tokens)
    assistant.content = text
    assistant.status = Message.Status.COMPLETE
    assistant.stop_reason = done.stop_reason
    assistant.model_id = done.model_id or spec.id
    assistant.input_tokens = done.usage.input_tokens
    assistant.output_tokens = done.usage.output_tokens
    assistant.cost_usd = cost
    if done.stop_reason == "refusal" and not text:
        assistant.status = Message.Status.ERROR
        assistant.error_kind = "refusal"
        assistant.error_message = "The model declined to answer this request."
    await assistant.asave()
    await UsageRecord.objects.acreate(
        user=user, conversation=conversation, provider=spec.provider, model_id=assistant.model_id,
        input_tokens=done.usage.input_tokens, output_tokens=done.usage.output_tokens, cost_usd=cost,
    )
    conversation.model_id = spec.id
    await conversation.asave(update_fields=["model_id", "updated_at"])


async def _record_stopped(user, conversation, assistant, spec, history, text) -> None:
    input_est = approx_tokens(system_prompt()) + sum(approx_tokens(m.content) for m in history)
    output_est = approx_tokens(text) if text else 0
    assistant.content = text
    assistant.status = Message.Status.STOPPED
    assistant.stop_reason = "stopped"
    await assistant.asave()
    await UsageRecord.objects.acreate(
        user=user, conversation=conversation, provider=spec.provider, model_id=spec.id,
        input_tokens=input_est, output_tokens=output_est,
        cost_usd=spec.estimate_cost(input_est, output_est), estimated=True,
    )


def _message_summary(m: Message) -> dict:
    return {
        "assistant_message_id": m.pk,
        "status": m.status,
        "model_id": m.model_id,
        "stop_reason": m.stop_reason,
        "input_tokens": m.input_tokens,
        "output_tokens": m.output_tokens,
        "cost_usd": str(m.cost_usd) if m.cost_usd is not None else None,
        "error_kind": m.error_kind,
        "error_message": m.error_message,
        "citations": m.citations,
        "invalid_citations": m.invalid_citations,
        "first_token_ms": m.first_token_ms,
        "duration_ms": m.duration_ms,
    }


def title_from(content: str) -> str:
    line = " ".join(content.split())
    return (line[:60] + "…") if len(line) > 60 else (line or DEFAULT_TITLE)
