from django.conf import settings
from django.db import models


class UsageRecord(models.Model):
    """One row per provider call. This is the ledger that cost reporting and quotas are computed from."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="usage_records")
    conversation = models.ForeignKey("chat.Conversation", null=True, blank=True, on_delete=models.SET_NULL)
    provider = models.CharField(max_length=40)
    model_id = models.CharField(max_length=120)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    # Null when the model's price is unverified; never silently recorded as zero.
    cost_usd = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    # True when tokens were estimated locally (e.g. the user stopped the stream before the provider reported usage).
    estimated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["user", "created_at"])]
        ordering = ["-created_at"]


class UsageLimit(models.Model):
    """Per-user overrides of the deployment-wide defaults in settings. Blank means 'use the default'."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="usage_limit")
    daily_token_limit = models.PositiveIntegerField(null=True, blank=True)
    monthly_cost_limit_usd = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_blocked = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
