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
