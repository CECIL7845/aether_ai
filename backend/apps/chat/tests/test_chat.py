import asyncio
import json
from decimal import Decimal

import pytest
import pytest_asyncio
from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.db import connections
from django.test import AsyncClient

from apps.accounts.models import User
from apps.chat.models import Conversation, Message
from apps.chat.services import build_history, generate_reply
from apps.providers.base import ProviderError
from apps.providers.registry import get_model
from apps.usage.models import UsageLimit, UsageRecord

pytestmark = pytest.mark.django_db(transaction=True)


@pytest_asyncio.fixture(autouse=True)
async def _close_async_db_connections():
    """The async ORM runs queries on a worker thread; close its connection so the test DB can be dropped."""
    yield
    await sync_to_async(connections.close_all)()


def parse_sse(body: bytes) -> list[tuple[str, dict]]:
    events = []
    for block in body.decode().strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


async def read(response) -> list[tuple[str, dict]]:
    assert response.status_code == 200, getattr(response, "content", b"")
    assert response["Content-Type"] == "text/event-stream"
    return parse_sse(b"".join([chunk async for chunk in response.streaming_content]))


async def make_user(email="ama@example.com"):
    return await sync_to_async(User.objects.create_user)(email, "correct-horse-battery-9")


async def logged_in(user) -> AsyncClient:
    client = AsyncClient()
    await client.aforce_login(user)
    return client


async def send(client, conversation_id, content="Hi there", **extra):
    return await client.post(
        f"/api/conversations/{conversation_id}/messages/",
        {"content": content, **extra},
        content_type="application/json",
    )


async def test_send_streams_reply_and_persists_everything(scripted):
    user = await make_user()
    conv = await Conversation.objects.acreate(user=user)
    events = await read(await send(await logged_in(user), conv.pk, "What is RAG?"))

    names = [e[0] for e in events]
    assert names == ["user_message", "start", "status", "delta", "delta", "done"]
    assert "".join(d["text"] for n, d in events if n == "delta") == "Hello, world."
    done = events[-1][1]
    assert done["input_tokens"] == 100 and done["output_tokens"] == 20
    assert Decimal(done["cost_usd"]) == Decimal("0.0004")  # 100*$2/M + 20*$10/M

    msgs = [m async for m in conv.messages.all()]
    assert [(m.role, m.content, m.status) for m in msgs] == [
        ("user", "What is RAG?", "complete"),
        ("assistant", "Hello, world.", "complete"),
    ]
    record = await UsageRecord.objects.aget(user=user)
    assert (record.input_tokens, record.output_tokens, record.estimated) == (100, 20, False)
    assert events[2][1] == {"stage": "generating", "provider": "scripted"}
    reply = msgs[1]
    assert reply.first_token_ms is not None and reply.duration_ms >= reply.first_token_ms
    await conv.arefresh_from_db()
    assert conv.title == "What is RAG?"
    assert conv.model_id == "scripted-model"


async def test_history_and_system_prompt_are_sent_to_provider(scripted):
    user = await make_user()
    conv = await Conversation.objects.acreate(user=user)
    client = await logged_in(user)
    await read(await send(client, conv.pk, "First"))
    await read(await send(client, conv.pk, "Second"))
    last = scripted.calls[-1]
    assert [(m.role, m.content) for m in last["messages"]] == [
        ("user", "First"),
        ("assistant", "Hello, world."),
        ("user", "Second"),
    ]
    assert "If you are unsure" in last["system"]


async def test_users_cannot_touch_each_others_conversations(scripted):
    owner = await make_user("owner@example.com")
    intruder = await make_user("intruder@example.com")
    conv = await Conversation.objects.acreate(user=owner, title="Private plans")
    msg = await Message.objects.acreate(conversation=conv, role="user", content="secret")
    client = await logged_in(intruder)

    assert (await send(client, conv.pk)).status_code == 404
    assert (await client.post(f"/api/conversations/{conv.pk}/regenerate/", {}, content_type="application/json")
            ).status_code == 404
    edit = await client.post(f"/api/conversations/{conv.pk}/messages/{msg.pk}/edit/", {"content": "x"},
                             content_type="application/json")
    assert edit.status_code == 404
    assert (await client.get(f"/api/conversations/{conv.pk}/")).status_code == 404
    assert (await client.get(f"/api/conversations/{conv.pk}/export/")).status_code == 404
    assert (await client.delete(f"/api/conversations/{conv.pk}/")).status_code == 404
    listing = (await client.get("/api/conversations/")).json()
    assert listing["count"] == 0
    search = (await client.get("/api/conversations/?q=secret")).json()
    assert search["count"] == 0
    assert scripted.calls == []


async def test_provider_error_is_reported_and_retry_replaces_failed_reply(scripted):
    user = await make_user()
    conv = await Conversation.objects.acreate(user=user)
    client = await logged_in(user)
    scripted.error = ProviderError("rate_limit", "Rate limit reached.", "scripted", 429, True)
    scripted.error_after = 1
    events = await read(await send(client, conv.pk))

    assert [e[0] for e in events] == ["user_message", "start", "status", "delta", "error"]
    assert events[-1][1]["kind"] == "rate_limit" and events[-1][1]["retryable"] is True
    failed = await conv.messages.aget(role="assistant")
    assert failed.status == "error" and failed.content == "Hello"
    assert await UsageRecord.objects.acount() == 0

    scripted.reset()
    events = await read(await client.post(f"/api/conversations/{conv.pk}/regenerate/", {},
                                          content_type="application/json"))
    assert events[-1][0] == "done"
    replies = [m async for m in conv.messages.filter(role="assistant")]
    assert [(m.status, m.content) for m in replies] == [("complete", "Hello, world.")]


async def test_failed_reply_is_excluded_from_next_prompt(scripted):
    user = await make_user()
    conv = await Conversation.objects.acreate(user=user)
    client = await logged_in(user)
    scripted.error = ProviderError("unavailable", "down", "scripted", 503, True)
    await read(await send(client, conv.pk, "First"))
    scripted.reset()
    await read(await send(client, conv.pk, "Second"))
    # The failed assistant turn is dropped and the two user turns are merged so roles still alternate.
    assert [(m.role, m.content) for m in scripted.calls[-1]["messages"]] == [("user", "First\n\nSecond")]


async def test_daily_token_quota_blocks_generation(scripted, settings):
    settings.USER_DAILY_TOKEN_LIMIT = 50
    user = await make_user()
    conv = await Conversation.objects.acreate(user=user)
    await UsageRecord.objects.acreate(user=user, provider="scripted", model_id="m", input_tokens=40, output_tokens=10)
    events = await read(await send(await logged_in(user), conv.pk))
    assert events[-1] == ("error", {"kind": "quota", "message": events[-1][1]["message"]})
    assert "token limit" in events[-1][1]["message"]
    assert scripted.calls == []


async def test_monthly_cost_quota_and_per_user_override(scripted, settings):
    settings.USER_MONTHLY_COST_LIMIT_USD = "1.00"
    user = await make_user()
    conv = await Conversation.objects.acreate(user=user)
    await UsageRecord.objects.acreate(user=user, provider="scripted", model_id="m", cost_usd=Decimal("1.50"))
    client = await logged_in(user)
    assert (await read(await send(client, conv.pk)))[-1][1]["kind"] == "quota"

    await UsageLimit.objects.acreate(user=user, monthly_cost_limit_usd=Decimal("5.00"))
    assert (await read(await send(client, conv.pk)))[-1][0] == "done"


async def test_blocked_user_and_global_cap(scripted, settings):
    user = await make_user()
    conv = await Conversation.objects.acreate(user=user)
    client = await logged_in(user)
    limit = await UsageLimit.objects.acreate(user=user, is_blocked=True)
    assert "paused" in (await read(await send(client, conv.pk)))[-1][1]["message"]

    await limit.adelete()
    settings.GLOBAL_MONTHLY_COST_LIMIT_USD = "0.50"
    other = await make_user("other@example.com")
    await UsageRecord.objects.acreate(user=other, provider="scripted", model_id="m", cost_usd=Decimal("0.60"))
    assert "workspace" in (await read(await send(client, conv.pk)))[-1][1]["message"]


async def test_input_validation(scripted, settings):
    settings.MAX_USER_MESSAGE_CHARS = 10
    user = await make_user()
    conv = await Conversation.objects.acreate(user=user)
    client = await logged_in(user)
    assert (await send(client, conv.pk, "   ")).status_code == 400
    assert (await send(client, conv.pk, "x" * 11)).status_code == 400
    bad_json = await client.post(f"/api/conversations/{conv.pk}/messages/", "{not json",
                                 content_type="application/json")
    assert bad_json.status_code == 400
    unknown_model = await send(client, conv.pk, "hi", model_id="does-not-exist")
    assert unknown_model.status_code == 400
    assert await conv.messages.acount() == 0


async def test_rate_limit(scripted, settings):
    settings.USER_GENERATIONS_PER_MINUTE = 2
    user = await make_user()
    conv = await Conversation.objects.acreate(user=user)
    client = await logged_in(user)
    for _ in range(2):
        await read(await send(client, conv.pk))
    assert (await send(client, conv.pk)).status_code == 429


async def test_only_one_generation_at_a_time(scripted):
    user = await make_user()
    conv = await Conversation.objects.acreate(user=user)
    await cache.aset(f"gen-lock:{user.pk}", 1, timeout=60)
    events = await read(await send(await logged_in(user), conv.pk))
    assert events[-1][1]["kind"] == "busy"


async def test_edit_discards_later_messages_and_regenerates(scripted):
    user = await make_user()
    conv = await Conversation.objects.acreate(user=user)
    client = await logged_in(user)
    await read(await send(client, conv.pk, "One"))
    await read(await send(client, conv.pk, "Two"))
    first = await conv.messages.filter(role="user").afirst()
    scripted.chunks = ["Edited answer"]
    events = await read(await client.post(f"/api/conversations/{conv.pk}/messages/{first.pk}/edit/",
                                          {"content": "One (edited)"}, content_type="application/json"))
    assert events[-1][0] == "done"
    assert [(m.role, m.content) async for m in conv.messages.all()] == [
        ("user", "One (edited)"),
        ("assistant", "Edited answer"),
    ]


async def test_cannot_edit_assistant_message(scripted):
    user = await make_user()
    conv = await Conversation.objects.acreate(user=user)
    client = await logged_in(user)
    await read(await send(client, conv.pk))
    reply = await conv.messages.aget(role="assistant")
    r = await client.post(f"/api/conversations/{conv.pk}/messages/{reply.pk}/edit/", {"content": "x"},
                          content_type="application/json")
    assert r.status_code == 404


async def test_stop_keeps_partial_answer_and_charges_an_estimate(scripted):
    user = await make_user()
    conv = await Conversation.objects.acreate(user=user)
    await Message.objects.acreate(conversation=conv, role="user", content="Tell me a long story")
    scripted.chunks = ["Once upon a time", " there was", " more", " text"]
    scripted.delay = 0.05
    received = []

    async def consume():
        async for chunk in generate_reply(user, conv, get_model("scripted-model")):
            received.append(chunk)

    task = asyncio.create_task(consume())
    async with asyncio.timeout(10):
        while not any("Once upon" in c for c in received):
            await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    reply = await conv.messages.aget(role="assistant")
    assert reply.status == "stopped"
    assert reply.content.startswith("Once upon a time")
    record = await UsageRecord.objects.aget(user=user)
    assert record.estimated is True and record.output_tokens > 0
    assert await cache.aget(f"gen-lock:{user.pk}") is None  # lock released


async def test_refusal_without_text_is_marked_as_error(scripted):
    user = await make_user()
    conv = await Conversation.objects.acreate(user=user)
    scripted.chunks = []
    scripted.stop_reason = "refusal"
    await read(await send(await logged_in(user), conv.pk))
    reply = await conv.messages.aget(role="assistant")
    assert reply.status == "error" and reply.error_kind == "refusal"


async def test_streaming_endpoints_require_auth_and_csrf(scripted):
    user = await make_user()
    conv = await Conversation.objects.acreate(user=user)
    assert (await send(AsyncClient(), conv.pk)).status_code == 403

    csrf_client = AsyncClient(enforce_csrf_checks=True)
    await csrf_client.aforce_login(user)
    assert (await send(csrf_client, conv.pk)).status_code == 403
    assert scripted.calls == []


async def test_build_history_trims_oldest_turns_to_budget():
    user = await make_user()
    conv = await Conversation.objects.acreate(user=user)
    for i in range(6):
        await Message.objects.acreate(conversation=conv, role="user" if i % 2 == 0 else "assistant",
                                      content=f"{i}" * 400)  # ≈100 tokens each
    history = await build_history(conv, budget_tokens=250)
    assert [m.content[0] for m in history] == ["4", "5"]
