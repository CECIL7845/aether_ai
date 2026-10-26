import pytest
import pytest_asyncio
from asgiref.sync import sync_to_async
from django.db import connections
from django.test import AsyncClient

from apps.accounts.models import User
from apps.chat.models import Conversation
from apps.documents.retrieval import Source
from apps.research.research import ResearchError

from .test_chat import read

pytestmark = pytest.mark.django_db(transaction=True)


@pytest_asyncio.fixture(autouse=True)
async def _close_async_db_connections():
    yield
    await sync_to_async(connections.close_all)()


WEB = [
    Source("W1", None, None, "Bank of Ghana", "bog.gov.gh", "The policy rate is 25 percent.", url="https://bog.gov.gh/x",
           kind="web"),
    Source("W2", None, None, "Blog", "blog.test · search snippet only", "Rate might be 27%.", url="https://blog.test",
           kind="web", retrieved=False),
]


@pytest.fixture
def fake_research(monkeypatch):
    calls = []

    def fake(user, question):
        calls.append(question)
        return WEB, {"query": question, "pages": [{"ref": "W1", "url": "https://bog.gov.gh/x", "status": "read"}]}

    monkeypatch.setattr("apps.chat.grounding.research", fake)
    return calls


async def start():
    user = await sync_to_async(User.objects.create_user)("ama@example.com", "correct-horse-battery-9")
    conv = await Conversation.objects.acreate(user=user)
    client = AsyncClient()
    await client.aforce_login(user)
    return conv, client


async def post(client, conv, content, **body):
    return await client.post(f"/api/conversations/{conv.pk}/messages/", {"content": content, **body},
                             content_type="application/json")


async def test_web_search_grounds_reply_and_validates_web_citations(scripted, fake_research):
    conv, client = await start()
    scripted.chunks = ["The rate is 25% [W1], though one blog claims 27% [W2]. See also [W7]."]
    events = await read(await post(client, conv, "What is Ghana's policy rate?", web_search=True))

    assert fake_research == ["What is Ghana's policy rate?"]
    stages = [d["stage"] for e, d in events if e == "status"]
    assert stages == ["searching_web", "generating"]
    assert [e for e, _ in events].index("start") < [e for e, _ in events].index("sources")
    info = next(d for e, d in events if e == "sources")
    assert [s["ref"] for s in info["web"]["sources"]] == ["W1", "W2"] and "mode" not in info
    call = scripted.calls[-1]
    assert "<web_results>" in call["messages"][-1].content and "<documents>" not in call["messages"][-1].content
    assert 'url="https://bog.gov.gh/x"' in call["messages"][-1].content
    assert 'retrieved="false"' in call["messages"][-1].content
    assert "Web pages can be outdated" in call["system"]
    done = events[-1][1]
    assert [c["ref"] for c in done["citations"]] == ["W1", "W2"]
    assert done["citations"][0]["url"] == "https://bog.gov.gh/x"
    assert done["invalid_citations"] == ["W7"]


async def test_web_search_off_by_default(scripted, fake_research):
    conv, client = await start()
    await read(await post(client, conv, "Hello"))
    assert fake_research == []
    assert "<web_results>" not in scripted.calls[-1]["messages"][-1].content


async def test_search_failure_is_reported_and_model_told(scripted, monkeypatch):
    def failing(user, question):
        raise ResearchError("You have reached your daily web search limit.")

    monkeypatch.setattr("apps.chat.grounding.research", failing)
    conv, client = await start()
    events = await read(await post(client, conv, "latest news?", web_search=True))
    info = next(d for e, d in events if e == "sources")
    assert info["web"]["error"] == "You have reached your daily web search limit."
    assert "Web search returned no usable results" in scripted.calls[-1]["messages"][-1].content
    assert events[-1][0] == "done"


async def test_models_endpoint_reports_web_search_feature(scripted, settings):
    conv, client = await start()
    data = (await client.get("/api/models/")).json()
    assert data["features"]["web_search"] is False  # no search key in tests
