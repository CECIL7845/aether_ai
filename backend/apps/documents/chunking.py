"""Splits extracted segments into overlapping chunks while keeping page/location attribution."""

from __future__ import annotations

from dataclasses import dataclass

from .extract import Segment

CHUNK_CHARS = 3_000  # ≈750 tokens
OVERLAP_CHARS = 400


@dataclass(frozen=True)
class ChunkDraft:
    text: str
    page_start: int | None
    page_end: int | None
    location: str


def _split_long(text: str) -> list[str]:
    """Split text longer than CHUNK_CHARS at paragraph, then sentence, then hard boundaries, with overlap."""
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + CHUNK_CHARS)
        if end < len(text):
            window = text[start:end]
            cut = max(window.rfind("\n\n"), window.rfind(". "), window.rfind("\n"))
            if cut > CHUNK_CHARS // 2:
                end = start + cut + 1
        pieces.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - OVERLAP_CHARS, start + 1)
    return [p for p in pieces if p]


def _location(segments: list[Segment]) -> tuple[int | None, int | None, str]:
    pages = [s.page for s in segments if s.page is not None]
    if pages:
        first, last = min(pages), max(pages)
        return first, last, f"Page {first}" if first == last else f"Pages {first}–{last}"
    labels = list(dict.fromkeys(s.location for s in segments if s.location))
    return None, None, "; ".join(labels)[:200]


def chunk_segments(segments: list[Segment]) -> list[ChunkDraft]:
    """Packs small segments together and splits large ones, so chunks are roughly CHUNK_CHARS each."""
    drafts: list[ChunkDraft] = []
    group: list[Segment] = []
    size = 0

    def flush():
        nonlocal group, size
        if group:
            first, last, loc = _location(group)
            drafts.append(ChunkDraft("\n\n".join(s.text for s in group), first, last, loc))
        group, size = [], 0

    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        if len(text) > CHUNK_CHARS:
            flush()
            first, last, loc = _location([segment])
            drafts += [ChunkDraft(piece, first, last, loc) for piece in _split_long(text)]
            continue
        if size + len(text) > CHUNK_CHARS:
            flush()
        group.append(Segment(text, segment.page, segment.location))
        size += len(text) + 2
    flush()
    return drafts
