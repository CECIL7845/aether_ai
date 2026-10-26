from django.contrib import admin

from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    # Metadata only: document content is not exposed in the admin.
    list_display = ("id", "user", "title", "kind", "size", "status", "chunk_count", "created_at")
    list_filter = ("status", "kind")
    search_fields = ("user__email", "title")
    exclude = ("file",)
    readonly_fields = [f.name for f in Document._meta.fields if f.name != "file"]
