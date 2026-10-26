"""Quota enforcement. Checked before every provider call so a user cannot run up unbounded AI spend."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from .models import UsageLimit, UsageRecord


@dataclass(frozen=True)
class QuotaStatus:
    allowed: bool
    reason: str = ""
    tokens_today: int = 0
    daily_token_limit: int = 0
    cost_this_month: Decimal = Decimal(0)
    monthly_cost_limit: Decimal = Decimal(0)


def _month_start(now):
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def check_quota(user) -> QuotaStatus:
    now = timezone.now()
    limit = await UsageLimit.objects.filter(user=user).afirst()
    daily_limit = (limit and limit.daily_token_limit) or settings.USER_DAILY_TOKEN_LIMIT
    monthly_limit = Decimal((limit and limit.monthly_cost_limit_usd) or settings.USER_MONTHLY_COST_LIMIT_USD)

    day = await UsageRecord.objects.filter(user=user, created_at__gte=now - timedelta(hours=24)).aaggregate(
        i=Sum("input_tokens"), o=Sum("output_tokens")
    )
    tokens_today = (day["i"] or 0) + (day["o"] or 0)
    month = await UsageRecord.objects.filter(user=user, created_at__gte=_month_start(now)).aaggregate(
        c=Sum("cost_usd")
    )
    cost = month["c"] or Decimal(0)
    status = dict(
        tokens_today=tokens_today, daily_token_limit=daily_limit, cost_this_month=cost, monthly_cost_limit=monthly_limit
    )

    if limit and limit.is_blocked:
        return QuotaStatus(False, "Your account's AI access has been paused by an administrator.", **status)
    if tokens_today >= daily_limit:
        return QuotaStatus(False, "You have reached your 24-hour token limit. Try again later.", **status)
    if cost >= monthly_limit:
        return QuotaStatus(False, "You have reached your monthly AI spending limit.", **status)

    global_limit = settings.GLOBAL_MONTHLY_COST_LIMIT_USD
    if global_limit:
        total = await UsageRecord.objects.filter(created_at__gte=_month_start(now)).aaggregate(c=Sum("cost_usd"))
        if (total["c"] or Decimal(0)) >= Decimal(global_limit):
            return QuotaStatus(False, "This workspace has reached its monthly AI spending limit.", **status)
    return QuotaStatus(True, **status)
