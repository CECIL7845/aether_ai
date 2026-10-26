"""Hybrid retrieval (vector + full-text) over a user's own documents, merged with reciprocal-rank fusion."""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import F
from pgvector.django import CosineDistance

from apps.providers.base import ProviderError
from apps.providers.embeddings import get_embedder

from .models import Chunk, Document


@dataclass(frozen=True)
class Source:
    """A numbered excerpt given to the model; the model cites it as [S<n>]."""

    ref: str
    chunk_id: int
    document_id: int
    title: str
    location: str
    text: str

    def public(self, snippet_chars: int = 280) -> dict:
        snippet = " ".join(self.text.split())
        return {
            "ref": self.ref,
            "document_id": self.document_id,
            "title": self.title,
            "location": self.location,
            "snippet": snippet[:snippet_chars] + ("…" if len(snippet) > snippet_chars else ""),
        }


def _number(chunks: list[Chunk]) -> list[Source]:
    return [
        Source(f"S{i}", c.pk, c.document_id, c.document.title, c.location, c.text)
        for i, c in enumerate(chunks, start=1)
    ]


def full_context(user, document_ids: list[int]) -> list[Source] | None:
    """All chunks in document order, if the attached documents are small enough to send in full."""
    docs = Document.objects.filter(user=user, pk__in=document_ids, status=Document.Status.READY)
    if sum(d.char_count for d in docs) > settings.FULL_CONTEXT_MAX_CHARS:
        return None
    chunks = list(
        Chunk.objects.filter(user=user, document__in=docs).select_related("document").order_by("document_id", "index")
    )
    return _number(chunks)


def search(user, document_ids: list[int], query: str, k: int | None = None) -> list[Source]:
    k = k or settings.RETRIEVAL_TOP_K
    base = Chunk.objects.filter(
        user=user, document_id__in=document_ids, document__user=user, document__status=Document.Status.READY
    ).select_related("document")
    ranked: dict[int, float] = {}
    by_id: dict[int, Chunk] = {}

    def fuse(results):
        for rank, chunk in enumerate(results):
            by_id[chunk.pk] = chunk
            ranked[chunk.pk] = ranked.get(chunk.pk, 0.0) + 1.0 / (60 + rank)

    pool = max(20, k * 3)
    # Match ANY meaningful term (questions rarely contain every word of the answer); ranking orders the hits.
    terms = list(dict.fromkeys(w for w in re.findall(r"\w+", query.lower()) if len(w) > 2))[:32]
    if terms:
        keyword = SearchQuery(" or ".join(terms), search_type="websearch", config="english")
        fuse(base.filter(search=keyword).annotate(rank=SearchRank(F("search"), keyword)).order_by("-rank")[:pool])

    embedder = get_embedder()
    if embedder is not None and base.filter(embedding__isnull=False).exists():
        try:
            [vector] = embedder.embed([query], "query")
            fuse(base.filter(embedding__isnull=False).order_by(CosineDistance("embedding", vector))[:pool])
        except ProviderError:
            pass  # degrade to keyword-only results

    best = sorted(ranked, key=ranked.get, reverse=True)[:k]
    # Present excerpts in document order so the model reads them coherently.
    chunks = sorted((by_id[i] for i in best), key=lambda c: (c.document_id, c.index))
    return _number(chunks)
