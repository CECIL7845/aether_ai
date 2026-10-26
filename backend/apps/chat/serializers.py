from rest_framework import serializers

from apps.providers.registry import available_models

from .models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = (
            "id", "role", "content", "status", "error_kind", "error_message", "model_id", "stop_reason",
            "input_tokens", "output_tokens", "cost_usd", "created_at",
        )
        read_only_fields = fields


class ConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ("id", "title", "model_id", "archived", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

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
