import httpx
import pytest

from apps.accounts.models import User
from apps.research import research as research_module
from apps.research.fetch import Fetcher
from apps.research.research import ResearchError, research
from apps.research.search import SearchResult, set_search_override
from apps.usage.models import UsageRecord

from .test_fetch import PAGE, resolver

pytestmark = pytest.mark.django_db


class FakeSearch:
    """TEST FIXTURE ONLY: canned search results (no network)."""

    name = "fake-search"

    def __init__(self, results):
        self.results = results
        self.queries = []

    def search(self, query, max_results):
        self.queries.append(query)
        return self.results[:max_results]


ROUTES = {
    "https://example.test/robots.txt": httpx.Response(404),
    "https://example.test/cocoa": httpx.Response(200, html=PAGE),
    "https://news.test/robots.txt": httpx.Response(404),
}


@pytest.fixture
def web():
    def factory():
        return Fetcher(resolver=resolver, transport=httpx.MockTransport(lambda r: ROUTES.get(str(r.url),
                                                                                             httpx.Response(500))))

    search = FakeSearch([
        SearchResult("Cocoa prices", "https://example.test/cocoa", "snippet A", "2026-10-01"),
        SearchResult("Broken page", "https://news.test/down", "Farmgate price announced at GH¢ 49,600 per tonne."),
        SearchResult("Internal", "http://evil.test/", ""),
    ])
    set_search_override(search)
    research_module.set_fetcher_factory(factory)
    yield search
    set_search_override(None)
    research_module.set_fetcher_factory(Fetcher)


@pytest.fixture
def user():
    return User.objects.create_user("ama@example.com", "correct-horse-battery-9")


def test_research_reads_pages_and_numbers_sources(web, user):
    sources, info = research(user, "  Ghana cocoa   farmgate price  ")
    assert web.queries == ["Ghana cocoa farmgate price"]
    assert [s.ref for s in sources] == ["W1", "W2"]
    read, snippet = sources
    assert read.retrieved and read.url == "https://example.test/cocoa" and "farmgate prices rose" in read.text
    assert read.location == "example.test · published 2026-10-01"
    assert not snippet.retrieved and "search snippet only" in snippet.location and "49,600" in snippet.text
    statuses = {p["url"]: p["status"] for p in info["pages"]}
    assert statuses == {"https://example.test/cocoa": "read", "https://news.test/down": "snippet",
                        "http://evil.test/": "failed"}
    assert UsageRecord.objects.filter(user=user, provider="search").count() == 1


def test_daily_search_limit(web, user, settings):
    settings.WEB_SEARCHES_PER_DAY = 1
    research(user, "first")
    with pytest.raises(ResearchError, match="daily web search limit"):
        research(user, "second")


def test_unconfigured_search(user):
    with pytest.raises(ResearchError, match="not configured"):
        research(user, "anything")
