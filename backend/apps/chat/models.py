from django.conf import settings
from django.db import models


class Conversation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations")
    title = models.CharField(max_length=200, default="New conversation")
    model_id = models.CharField(max_length=120, blank=True)
    archived = models.BooleanField(default=False)
    # Documents the assistant may use when answering in this conversation.
    documents = models.ManyToManyField("documents.Document", blank=True, related_name="conversations")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["user", "archived", "-updated_at"])]

    def __str__(self):
        return self.title


class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user"
        ASSISTANT = "assistant"

    class Status(models.TextChoices):
        COMPLETE = "complete"
        STREAMING = "streaming"
        STOPPED = "stopped"  # user pressed stop; partial content kept
        ERROR = "error"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.COMPLETE)
    error_kind = models.CharField(max_length=40, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    model_id = models.CharField(max_length=120, blank=True)
    stop_reason = models.CharField(max_length=40, blank=True)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    cost_usd = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    # Sources the reply actually cited ([S1] ...), validated against the excerpts it was given.
    citations = models.JSONField(default=list, blank=True)
    # Citation markers in the reply that did not match any provided source (a sign of fabrication).
    invalid_citations = models.JSONField(default=list, blank=True)
    # Latency observability: time from request to first streamed text, and to completion.
    first_token_ms = models.PositiveIntegerField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
