from django.contrib import admin

from .models import Conversation


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    # Metadata only: message content stays out of the admin to limit staff exposure to user data.
    list_display = ("id", "user", "model_id", "archived", "created_at", "updated_at")
    list_filter = ("archived",)
    search_fields = ("user__email",)
    readonly_fields = ("user", "title", "model_id", "created_at", "updated_at")
