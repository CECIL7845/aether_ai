from django.contrib import admin

from .models import UsageLimit, UsageRecord


@admin.register(UsageRecord)
class UsageRecordAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "provider", "model_id", "input_tokens", "output_tokens", "cost_usd")
    list_filter = ("provider", "model_id")
    search_fields = ("user__email",)
    date_hierarchy = "created_at"

    def has_change_permission(self, request, obj=None):
        return False  # the ledger is append-only


@admin.register(UsageLimit)
class UsageLimitAdmin(admin.ModelAdmin):
    list_display = ("user", "daily_token_limit", "monthly_cost_limit_usd", "is_blocked", "updated_at")
    search_fields = ("user__email",)
    autocomplete_fields = ("user",)
