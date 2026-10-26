"""Embedding providers for document retrieval. Separate from chat providers: not every chat provider offers
embeddings (Anthropic does not), and a deployment can run keyword-only search with EMBEDDING_PROVIDER=none."""

from __future__ import annotations

import math
from typing import Literal, Protocol

from django.conf import settings

from .base import ProviderError

TaskType = Literal["document", "query"]


class Embedder(Protocol):
    model: str

    def embed(self, texts: list[str], task: TaskType) -> list[list[float]]: ...


def _normalise(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class GeminiEmbedder:
    BATCH = 50

    def __init__(self) -> None:
        from google import genai
        from google.genai import types

        self._types = types
        self.model = settings.EMBEDDING_MODEL
        self._client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(
                timeout=60_000,
                retry_options=types.HttpRetryOptions(attempts=4, initial_delay=2.0, max_delay=20.0,
                                                     http_status_codes=[408, 429, 500, 502, 503, 504]),
            ),
        )

    def embed(self, texts: list[str], task: TaskType) -> list[list[float]]:
        from google.genai import errors

        config = self._types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT" if task == "document" else "RETRIEVAL_QUERY",
            output_dimensionality=settings.EMBEDDING_DIMENSIONS,
        )
        vectors: list[list[float]] = []
        try:
            for i in range(0, len(texts), self.BATCH):
                batch = texts[i : i + self.BATCH]
                result = self._client.models.embed_content(model=self.model, contents=batch, config=config)
                if len(result.embeddings or []) != len(batch):
                    raise ProviderError("bad_request", "Embedding count did not match input count.", "gemini")
                vectors += [_normalise(list(e.values)) for e in result.embeddings]
        except errors.ClientError as e:
            kind = "rate_limit" if e.code == 429 else "auth" if e.code in (401, 403) else "bad_request"
            raise ProviderError(kind, f"Embedding request failed ({e.code}).", "gemini", e.code) from e
        except errors.ServerError as e:
            raise ProviderError("unavailable", "Embedding service unavailable.", "gemini", e.code, True) from e
        return vectors


_override: Embedder | None = None


def get_embedder() -> Embedder | None:
    """The configured embedder, or None for keyword-only retrieval."""
    if _override is not None:
        return _override
    if settings.EMBEDDING_PROVIDER == "gemini" and settings.GEMINI_API_KEY:
        return GeminiEmbedder()
    return None


def set_embedder_override(embedder: Embedder | None) -> None:
    """Used by test fixtures to substitute a deterministic embedder."""
    global _override
    _override = embedder
