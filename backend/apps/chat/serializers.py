from rest_framework import serializers

from apps.documents.models import Document
from apps.providers.registry import available_models

from .models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = (
            "id", "role", "content", "status", "error_kind", "error_message", "model_id", "stop_reason",
            "input_tokens", "output_tokens", "cost_usd", "citations", "invalid_citations", "first_token_ms",
            "duration_ms", "created_at",
        )
        read_only_fields = fields


class AttachedDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ("id", "title", "kind", "status", "error")


class ConversationSerializer(serializers.ModelSerializer):
    document_ids = serializers.PrimaryKeyRelatedField(
        many=True, source="documents", queryset=Document.objects.none(), required=False
    )
    documents = AttachedDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = ("id", "title", "model_id", "archived", "document_ids", "documents", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        # Only the requesting user's own documents can be attached; anything else is "does not exist".
        user = getattr(request, "user", None)
        queryset = Document.objects.filter(user=user) if user and user.is_authenticated else Document.objects.none()
        fields["document_ids"].child_relation.queryset = queryset
        return fields

    def validate_title(self, value):
        value = " ".join(value.split())
        if not value:
            raise serializers.ValidationError("Title cannot be empty.")
        return value

    def validate_model_id(self, value):
        if value and value not in {m.id for m in available_models()}:
            raise serializers.ValidationError("This model is not available on this deployment.")
        return value


class ConversationDetailSerializer(ConversationSerializer):
    messages = MessageSerializer(many=True, read_only=True)

    class Meta(ConversationSerializer.Meta):
        fields = ConversationSerializer.Meta.fields + ("messages",)
