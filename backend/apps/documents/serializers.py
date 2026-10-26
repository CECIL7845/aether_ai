from rest_framework import serializers

from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = (
            "id", "title", "kind", "size", "status", "error", "page_count", "char_count", "chunk_count",
            "embedding_model", "created_at", "updated_at",
        )
        read_only_fields = fields
