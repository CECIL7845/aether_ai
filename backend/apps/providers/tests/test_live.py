"""Live smoke tests against real provider APIs.

Skipped unless RUN_LIVE_TESTS=1, because they need real keys and spend real (small) quota:
    RUN_LIVE_TESTS=1 uv run pytest apps/providers/tests/test_live.py -v
"""

import os

import pytest
from django.conf import settings

from apps.providers.base import ChatMessage, ProviderError, StreamDone, TextDelta
from apps.providers.registry import MODELS
from apps.providers.services import get_provider

pytestmark = [
    pytest.mark.skipif(os.environ.get("RUN_LIVE_TESTS") != "1", reason="set RUN_LIVE_TESTS=1 to call real APIs"),
]


@pytest.fixture(autouse=True)
def _real_keys(settings):
    """Unit-test settings blank the API keys; live tests put the real ones back."""
    settings.GEMINI_API_KEY = settings.LIVE_API_KEYS["gemini"]
    settings.ANTHROPIC_API_KEY = settings.LIVE_API_KEYS["anthropic"]
    settings.EMBEDDING_PROVIDER = "gemini"
    settings.TAVILY_API_KEY = settings.LIVE_API_KEYS["tavily"]


def _first_model(provider: str) -> str:
    return next(m.id for m in MODELS if m.provider == provider)


@pytest.mark.parametrize("provider_name", ["gemini", "anthropic"])
async def test_streams_a_real_reply(provider_name):
    provider = get_provider(provider_name)
    if not provider.is_configured():
        pytest.skip(f"{provider_name} has no API key configured")
    deltas, done = [], None
    async for event in provider.stream(
        model_id=_first_model(provider_name),
        messages=[ChatMessage("user", "Reply with exactly the word: pong")],
        system="You are a test endpoint. Follow instructions exactly.",
        max_output_tokens=1024,
    ):
        if isinstance(event, TextDelta):
            deltas.append(event.text)
        elif isinstance(event, StreamDone):
            done = event
    assert "pong" in "".join(deltas).lower()
    assert done is not None and done.usage.input_tokens > 0 and done.usage.output_tokens > 0


@pytest.mark.parametrize("provider_name", ["gemini", "anthropic"])
async def test_unknown_model_maps_to_not_found(provider_name):
    provider = get_provider(provider_name)
    if not provider.is_configured():
        pytest.skip(f"{provider_name} has no API key configured")
    with pytest.raises(ProviderError) as info:
        async for _ in provider.stream(model_id="no-such-model-xyz", messages=[ChatMessage("user", "hi")],
                                       system="", max_output_tokens=16):
            pass
    assert info.value.kind in ("not_found", "bad_request")
    assert not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY not in str(info.value)  # no key leaks


def test_gemini_embeddings_rank_the_relevant_text_first():
    from apps.providers.embeddings import GeminiEmbedder

    if not settings.GEMINI_API_KEY:
        pytest.skip("gemini has no API key configured")
    embedder = GeminiEmbedder()
    docs = embedder.embed(
        ["Shipping to Tamale takes four working days.", "Our refund policy allows returns within 30 days."],
        "document",
    )
    [query] = embedder.embed(["How long is delivery to Tamale?"], "query")
    scores = [sum(a * b for a, b in zip(query, d, strict=True)) for d in docs]
    assert len(docs[0]) == settings.EMBEDDING_DIMENSIONS
    assert scores[0] > scores[1]


def test_tavily_search_and_safe_fetch_of_a_real_page():
    from apps.research.fetch import Fetcher
    from apps.research.search import TavilySearch

    if not settings.TAVILY_API_KEY:
        pytest.skip("tavily has no API key configured")
    results = TavilySearch().search("Django web framework official documentation", 3)
    assert results and all(r.url.startswith("http") for r in results)
    fetcher = Fetcher()
    try:
        page = fetcher.fetch("https://docs.djangoproject.com/en/stable/")
    finally:
        fetcher.close()
    assert "Django" in page.text and page.url.startswith("https://docs.djangoproject.com/")


@pytest.mark.django_db(transaction=True)
async def test_gemini_uses_analysis_tools_for_numbers():
    from asgiref.sync import sync_to_async
    from django.db import connections

    from apps.accounts.models import User
    from apps.analysis.executor import AnalysisExecutor
    from apps.analysis.tests.test_tools import make_dataset
    from apps.analysis.tools import INSTRUCTIONS, SPECS, ToolContext
    from apps.chat.models import Conversation
    from apps.providers.base import ToolActivity

    if not settings.GEMINI_API_KEY:
        pytest.skip("gemini has no API key configured")
    user = await sync_to_async(User.objects.create_user)("live@example.com", "correct-horse-battery-9")
    conv = await Conversation.objects.acreate(user=user)
    doc = await sync_to_async(make_dataset)(user)
    executor = AnalysisExecutor(ToolContext(user=user, conversation=conv, datasets=[doc]))
    text, tools_used = [], []
    try:
        async for event in get_provider("gemini").stream(
            model_id="gemini-3.5-flash-lite",
            messages=[ChatMessage("user", "What is the total revenue for the Accra region? Use the tools.")],
            system="You are a data analyst." + INSTRUCTIONS,
            max_output_tokens=2048,
            tools=SPECS,
            execute=executor,
        ):
            if isinstance(event, TextDelta):
                text.append(event.text)
            elif isinstance(event, ToolActivity) and event.status != "running":
                tools_used.append((event.name, event.status))
    finally:
        await sync_to_async(connections.close_all)()
    answer = "".join(text).replace(",", "")
    assert ("query_dataset", "done") in tools_used, tools_used
    assert "1910.5" in answer, answer
