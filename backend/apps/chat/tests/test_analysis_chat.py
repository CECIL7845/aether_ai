import pytest
import pytest_asyncio
from asgiref.sync import sync_to_async
from django.db import connections
from django.test import AsyncClient

from apps.accounts.models import User
from apps.analysis.tests.test_tools import make_dataset
from apps.chat.models import Conversation

from .test_chat import read, send

pytestmark = pytest.mark.django_db(transaction=True)


@pytest_asyncio.fixture(autouse=True)
async def _close_async_db_connections():
    yield
    await sync_to_async(connections.close_all)()


async def setup():
    user = await sync_to_async(User.objects.create_user)("ama@example.com", "correct-horse-battery-9")
    doc = await sync_to_async(make_dataset)(user)
    conv = await Conversation.objects.acreate(user=user)
    await conv.documents.aadd(doc)
    client = AsyncClient()
    await client.aforce_login(user)
    return doc, conv, client


async def test_tool_loop_computes_numbers_and_stores_artifacts(scripted):
    doc, conv, client = await setup()
    scripted.tool_script = [
        ("list_datasets", {}),
        ("query_dataset", {"dataset_id": doc.pk, "group_by": ["region"],
                           "aggregations": [{"func": "sum", "column": "revenue"}], "title": "Revenue by region"}),
        ("query_dataset", {"dataset_id": doc.pk, "group_by": ["nope"]}),  # model error → tool error result
    ]
    scripted.chunks = ["Accra leads with 1,910.50 in revenue."]
    events = await read(await send(client, conv.pk, "Which region has the most revenue?"))

    call = scripted.calls[-1]
    assert {t.name for t in call["tools"]} == {"list_datasets", "describe_dataset", "query_dataset", "create_chart",
                                               "calculate"}
    assert "Never estimate or compute figures yourself" in call["system"]
    # Spreadsheet text is not pasted into the prompt; numbers come from tools.
    assert "<documents>" not in call["messages"][-1].content
    assert scripted.tool_results[1]["rows"][0] == ["Accra", 1910.5]
    assert "Unknown column 'nope'" in scripted.tool_results[2]["error"]

    tool_events = [d for e, d in events if e == "tool"]
    assert [(t["name"], t["status"]) for t in tool_events] == [
        ("list_datasets", "running"), ("list_datasets", "done"),
        ("query_dataset", "running"), ("query_dataset", "done"),
        ("query_dataset", "running"), ("query_dataset", "error"),
    ]
    done = events[-1][1]
    assert [a["type"] for a in done["artifacts"]] == ["table"]
    assert done["artifacts"][0]["rows"][0] == ["Accra", 1910.5]
    assert [c["status"] for c in done["tool_calls"]] == ["done", "done", "error"]


async def test_no_tools_without_datasets(scripted):
    user = await sync_to_async(User.objects.create_user)("x@example.com", "correct-horse-battery-9")
    conv = await Conversation.objects.acreate(user=user)
    client = AsyncClient()
    await client.aforce_login(user)
    await read(await send(client, conv.pk, "hello"))
    assert scripted.calls[-1]["tools"] is None
