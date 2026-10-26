"""Web research: search → fetch result pages (SSRF-safe) → pick relevant passages → numbered sources [W1]…"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.utils import timezone

from apps.documents.chunking import chunk_segments
from apps.documents.extract import Segment
from apps.documents.retrieval import Source
from apps.usage.models import UsageRecord

from .fetch import Fetcher, FetchError, Page
from .search import SearchError, SearchResult, get_search_provider


class ResearchError(Exception):
    pass


_fetcher_factory = Fetcher


def set_fetcher_factory(factory) -> None:
    """Used by tests to inject a fetcher with a fake resolver/transport."""
    global _fetcher_factory
    _fetcher_factory = factory


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", text.lower()) if len(w) > 2}


def _best_passages(page_text: str, query: str, max_chars: int) -> str:
    chunks = chunk_segments([Segment(page_text)])
    terms = _terms(query)
    ranked = sorted(chunks, key=lambda c: len(terms & _terms(c.text)), reverse=True)
    picked, size = [], 0
    for chunk in ranked:
        if size + len(chunk.text) > max_chars and picked:
            break
        picked.append(chunk.text[:max_chars])
        size += len(chunk.text)
    return "\n…\n".join(picked)


def _fetch_one(result: SearchResult) -> tuple[SearchResult, Page | None, str]:
    fetcher = _fetcher_factory()
    try:
        return result, fetcher.fetch(result.url), ""
    except FetchError as e:
        return result, None, str(e)
    finally:
        fetcher.close()


def research(user, query: str) -> tuple[list[Source], dict]:
    provider = get_search_provider()
    if provider is None:
        raise ResearchError("Web search is not configured on this workspace.")
    since = timezone.now() - timedelta(hours=24)
    used = UsageRecord.objects.filter(user=user, provider="search", created_at__gte=since).count()
    if used >= settings.WEB_SEARCHES_PER_DAY:
        raise ResearchError("You have reached your daily web search limit.")

    query = " ".join(query.split())[:400]
    try:
        results = provider.search(query, settings.WEB_SEARCH_RESULTS)
    except SearchError as e:
        raise ResearchError(str(e)) from e
    finally:
        UsageRecord.objects.create(user=user, provider="search", model_id=provider.name)

    with ThreadPoolExecutor(max_workers=4) as pool:
        fetched = list(pool.map(_fetch_one, results))

    sources: list[Source] = []
    pages = []
    for result, page, error in fetched:
        domain = urlsplit(page.url if page else result.url).hostname or ""
        ref = f"W{len(sources) + 1}"
        if page is not None:
            text = _best_passages(page.text, query, settings.WEB_MAX_CHARS_PER_PAGE)
            title = page.title or result.title
            location = domain + (f" · published {result.published[:10]}" if result.published else "")
            sources.append(Source(ref, None, None, title, location, text, url=page.url, kind="web"))
            pages.append({"ref": ref, "url": page.url, "title": title, "status": "read"})
        elif result.snippet:
            # Keep the search snippet so the model has something, but label it as unverified by us.
            location = f"{domain} · search snippet only (page not read: {error})"
            sources.append(Source(ref, None, None, result.title, location, result.snippet, url=result.url,
                                  kind="web", retrieved=False))
            pages.append({"ref": ref, "url": result.url, "title": result.title, "status": "snippet", "reason": error})
        else:
            pages.append({"url": result.url, "title": result.title, "status": "failed", "reason": error})
    return sources, {"query": query, "pages": pages}
