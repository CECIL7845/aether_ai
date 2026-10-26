"""Maintained model registry.

Capabilities and prices are declared per model rather than assumed, so the UI never offers a feature a model
lacks. Prices are USD per million tokens; `None` means the price has not been verified and cost is not estimated.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal

from django.conf import settings


@dataclass(frozen=True)
class ModelSpec:
    id: str
    provider: str
    label: str
    context_window: int
    max_output_tokens: int
    supports_vision: bool = False
    supports_tools: bool = False
    supports_fallbacks: bool = False
    input_price_per_mtok: Decimal | None = None
    output_price_per_mtok: Decimal | None = None
    price_source: str = ""

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> Decimal | None:
        if self.input_price_per_mtok is None or self.output_price_per_mtok is None:
            return None
        million = Decimal(1_000_000)
        return (
            Decimal(input_tokens) * self.input_price_per_mtok / million
            + Decimal(output_tokens) * self.output_price_per_mtok / million
        )

    def public_dict(self) -> dict:
        data = asdict(self)
        for key in ("input_price_per_mtok", "output_price_per_mtok"):
            data[key] = str(data[key]) if data[key] is not None else None
        return data


ANTHROPIC_PRICES = "Anthropic first-party list price, model table cached 2026-10-06"

MODELS: list[ModelSpec] = [
    ModelSpec(
        id="gemini-3.5-flash",
        provider="gemini",
        label="Gemini 3.5 Flash",
        # Limits from the Gemini Models API (input_token_limit / output_token_limit), checked 2026-10-26.
        context_window=1_048_576,
        max_output_tokens=65_536,
        supports_vision=True,
        supports_tools=True,
    ),
    ModelSpec(
        id="gemini-3.5-flash-lite",
        provider="gemini",
        label="Gemini 3.5 Flash-Lite",
        # Limits from the Gemini Models API (input_token_limit / output_token_limit), checked 2026-10-26.
        context_window=1_048_576,
        max_output_tokens=65_536,
        supports_vision=True,
        supports_tools=True,
    ),
    ModelSpec(
        id="gemini-flash-latest",
        provider="gemini",
        label="Gemini Flash (latest alias)",
        # Limits from the Gemini Models API (input_token_limit / output_token_limit), checked 2026-10-26.
        context_window=1_048_576,
        max_output_tokens=65_536,
        supports_vision=True,
        supports_tools=True,
    ),
    ModelSpec(
        id="gemini-flash-lite-latest",
        provider="gemini",
        label="Gemini Flash-Lite (latest alias)",
        # Limits from the Gemini Models API (input_token_limit / output_token_limit), checked 2026-10-26.
        context_window=1_048_576,
        max_output_tokens=65_536,
        supports_vision=True,
        supports_tools=True,
    ),
    ModelSpec(
        id="gemini-pro-latest",
        provider="gemini",
        label="Gemini Pro (latest alias; paid tier only)",
        # Limits from the Gemini Models API (input_token_limit / output_token_limit), checked 2026-10-26.
        context_window=1_048_576,
        max_output_tokens=65_536,
        supports_vision=True,
        supports_tools=True,
    ),
    ModelSpec(
        id="claude-opus-5-5",
        provider="anthropic",
        label="Claude Opus 5.5",
        context_window=1_000_000,
        max_output_tokens=128_000,
        supports_vision=True,
        supports_tools=True,
        supports_fallbacks=True,
        input_price_per_mtok=Decimal("4.00"),
        output_price_per_mtok=Decimal("20.00"),
        price_source=ANTHROPIC_PRICES,
    ),
    ModelSpec(
        id="claude-sonnet-5-5",
        provider="anthropic",
        label="Claude Sonnet 5.5",
        context_window=1_000_000,
        max_output_tokens=128_000,
        supports_vision=True,
        supports_tools=True,
        supports_fallbacks=True,
        input_price_per_mtok=Decimal("2.00"),
        output_price_per_mtok=Decimal("10.00"),
        price_source=ANTHROPIC_PRICES,
    ),
    ModelSpec(
        id="claude-haiku-5-5",
        provider="anthropic",
        label="Claude Haiku 5.5",
        context_window=1_000_000,
        max_output_tokens=128_000,
        supports_vision=True,
        supports_tools=True,
        # Prompts above 100K tokens are billed at $0.50 / $2.50; the estimate uses the base rate.
        input_price_per_mtok=Decimal("0.10"),
        output_price_per_mtok=Decimal("0.50"),
        price_source=ANTHROPIC_PRICES + " (prompts up to 100K tokens)",
    ),
]

_BY_ID = {m.id: m for m in MODELS}


def get_model(model_id: str) -> ModelSpec | None:
    return _BY_ID.get(model_id)


def available_models() -> list[ModelSpec]:
    """Models whose provider has credentials configured on this deployment."""
    from .services import get_provider

    return [m for m in MODELS if get_provider(m.provider).is_configured()]


def default_model() -> ModelSpec | None:
    models = available_models()
    preferred = get_model(settings.DEFAULT_MODEL) if settings.DEFAULT_MODEL else None
    if preferred and preferred in models:
        return preferred
    return models[0] if models else None
