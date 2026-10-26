import asyncio
from decimal import Decimal

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.providers.base import ProviderError, StreamDone, TextDelta, Usage
from apps.providers.registry import _BY_ID, MODELS, ModelSpec
from apps.providers.services import _PROVIDERS, register_provider


@pytest.fixture(autouse=True)
def _clear_cache():
    """Throttle counters and generation locks live in the cache; isolate them per test."""
    cache.clear()


@pytest.fixture
def api():
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def csrf_api(api):
    """APIClient that has fetched a CSRF cookie and sends it back like the SPA does."""
    api.get("/api/auth/csrf/")
    api.credentials(HTTP_X_CSRFTOKEN=api.cookies["csrftoken"].value)
    return api


# ---------------------------------------------------------------------------
# TEST FIXTURE ONLY: a scripted provider so chat flows can be tested without network access or API spend.
# It is never registered outside tests. Real-provider behaviour is covered by the live smoke test
# (apps/providers/tests/test_live.py), which runs only when real API keys are configured.
# ---------------------------------------------------------------------------


class ScriptedProvider:
    name = "scripted"

    def __init__(self):
        self.reset()

    def reset(self):
        self.chunks = ["Hello", ", world."]
        self.usage = Usage(input_tokens=100, output_tokens=20)
        self.stop_reason = "end"
        self.error: ProviderError | None = None
        self.error_after = 0
        self.delay = 0.0
        self.calls: list[dict] = []

    def is_configured(self):
        return True

    async def stream(self, *, model_id, messages, system, max_output_tokens):
        self.calls.append({"model_id": model_id, "messages": messages, "system": system})
        for i, chunk in enumerate(self.chunks):
            if self.error and i == self.error_after:
                raise self.error
            if self.delay:
                await asyncio.sleep(self.delay)
            yield TextDelta(chunk)
        if self.error and self.error_after >= len(self.chunks):
            raise self.error
        yield StreamDone(usage=self.usage, stop_reason=self.stop_reason, model_id=model_id)


SCRIPTED_SPEC = ModelSpec(
    id="scripted-model",
    provider="scripted",
    label="Scripted (test fixture)",
    context_window=10_000,
    max_output_tokens=1_000,
    input_price_per_mtok=Decimal("2"),
    output_price_per_mtok=Decimal("10"),
)


@pytest.fixture
def scripted(settings):
    """Registers the scripted provider and makes it the only available model."""
    settings.ANTHROPIC_API_KEY = ""
    settings.GEMINI_API_KEY = ""
    settings.DEFAULT_MODEL = SCRIPTED_SPEC.id
    provider = ScriptedProvider()
    register_provider(provider)
    MODELS.append(SCRIPTED_SPEC)
    _BY_ID[SCRIPTED_SPEC.id] = SCRIPTED_SPEC
    yield provider
    MODELS.remove(SCRIPTED_SPEC)
    _BY_ID.pop(SCRIPTED_SPEC.id, None)
    _PROVIDERS.pop("scripted", None)


# ---------------------------------------------------------------------------
# TEST FIXTURE ONLY: deterministic bag-of-words "embedder" so vector retrieval can be tested offline.
# Real embeddings (Gemini) are exercised by the live tests.
# ---------------------------------------------------------------------------
import hashlib  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402

from apps.providers.embeddings import set_embedder_override  # noqa: E402


class HashingEmbedder:
    model = "test-hashing-embedder"

    def __init__(self):
        self.calls = 0

    def embed(self, texts, task):
        self.calls += 1
        out = []
        for text in texts:
            v = [0.0] * 768
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                v[int(hashlib.sha256(word.encode()).hexdigest(), 16) % 768] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out


@pytest.fixture
def embedder():
    e = HashingEmbedder()
    set_embedder_override(e)
    yield e
    set_embedder_override(None)
