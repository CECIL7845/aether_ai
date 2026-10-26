"""Web search providers. Results are leads only; pages are fetched and read by `fetch.py` before citing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx
from django.conf import settings


class SearchError(Exception):
    pass


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    published: str = ""


class SearchProvider(Protocol):
    name: str

    def search(self, query: str, max_results: int) -> list[SearchResult]: ...


class TavilySearch:
    name = "tavily"
    URL = "https://api.tavily.com/search"

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        try:
            response = httpx.post(
                self.URL,
                headers={"Authorization": f"Bearer {settings.TAVILY_API_KEY}"},
                json={"query": query[:400], "max_results": max_results, "search_depth": "basic",
                      "include_published_date": True},
                timeout=20,
            )
        except httpx.HTTPError as e:
            raise SearchError("The search service could not be reached.") from e
        if response.status_code in (401, 403):
            raise SearchError("The search service rejected the API key.")
        if response.status_code == 429 or response.status_code == 432:
            raise SearchError("The search service quota or rate limit was reached.")
        if response.status_code >= 400:
            raise SearchError(f"The search service returned an error ({response.status_code}).")
        results = []
        for item in response.json().get("results", []):
            url = str(item.get("url") or "")
            if url.startswith(("http://", "https://")):
                results.append(SearchResult(title=str(item.get("title") or url)[:300], url=url,
                                            snippet=str(item.get("content") or "")[:2000],
                                            published=str(item.get("published_date") or "")[:40]))
        return results


_override: SearchProvider | None = None


def get_search_provider() -> SearchProvider | None:
    if _override is not None:
        return _override
    if settings.SEARCH_PROVIDER == "tavily" and settings.TAVILY_API_KEY:
        return TavilySearch()
    return None


def set_search_override(provider: SearchProvider | None) -> None:
    """Used by test fixtures."""
    global _override
    _override = provider
