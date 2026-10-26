import json

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.providers.registry import available_models, default_model, get_model

from .models import Conversation, Message
from .serializers import ConversationDetailSerializer, ConversationSerializer
from .services import DEFAULT_TITLE, check_rate, generate_reply, title_from


class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer

    def get_queryset(self):
        qs = Conversation.objects.filter(user=self.request.user).prefetch_related("documents")
        archived = self.request.query_params.get("archived")
        if archived in ("true", "false"):
            qs = qs.filter(archived=archived == "true")
        q = (self.request.query_params.get("q") or "").strip()[:200]
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(messages__content__icontains=q)).distinct()
        return qs

    def get_serializer_class(self):
        return ConversationDetailSerializer if self.action == "retrieve" else ConversationSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        conversation = self.get_object()
        fmt = request.query_params.get("fmt", "md")
        if fmt not in ("md", "txt"):
            return JsonResponse({"detail": "fmt must be 'md' or 'txt'."}, status=400)
        lines = [f"# {conversation.title}" if fmt == "md" else conversation.title, ""]
        for m in conversation.messages.exclude(status=Message.Status.ERROR):
            who = "You" if m.role == Message.Role.USER else (m.model_id or "Assistant")
            lines += [f"## {who}" if fmt == "md" else f"[{who}]", "", m.content, ""]
        name = slugify(conversation.title)[:60] or "conversation"
        response = HttpResponse("\n".join(lines), content_type="text/markdown; charset=utf-8"
                                if fmt == "md" else "text/plain; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{name}.{fmt}"'
        return response


# --- Streaming endpoints (plain async Django views: DRF views are sync-only) ---

def _error(status: int, detail: str) -> JsonResponse:
    return JsonResponse({"detail": detail}, status=status)


async def _parse(request) -> dict | None:
    try:
        data = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


async def _prepare(request, conversation_id: int):
    """Authenticate, load the user's own conversation, rate-limit and resolve the model."""
    user = await request.auser()
    if not user.is_authenticated:
        return None, _error(403, "Authentication required.")
    data = await _parse(request)
    if data is None:
        return None, _error(400, "Invalid JSON body.")
    conversation = await Conversation.objects.filter(pk=conversation_id, user=user).afirst()
    if conversation is None:
        return None, _error(404, "Conversation not found.")
    if not await check_rate(user.pk):
        return None, _error(429, "Too many requests. Please slow down.")
    model_id = data.get("model_id") or conversation.model_id
    spec = get_model(model_id) if model_id else default_model()
    if spec is None or spec not in available_models():
        return None, _error(400, "No AI model is available. Ask an administrator to configure a provider.")
    return (user, conversation, spec, data), None


def _validate_content(data: dict) -> str | JsonResponse:
    content = data.get("content")
    if not isinstance(content, str) or not content.strip():
        return _error(400, "Message content is required.")
    if len(content) > settings.MAX_USER_MESSAGE_CHARS:
        return _error(400, f"Message is too long (max {settings.MAX_USER_MESSAGE_CHARS} characters).")
    return content


def _stream(user, conversation, spec, extra_start: dict | None = None) -> StreamingHttpResponse:
    async def events():
        if extra_start:
            from .services import sse

            yield sse("user_message", extra_start)
        async for chunk in generate_reply(user, conversation, spec):
            yield chunk

    response = StreamingHttpResponse(events(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # disable proxy buffering (nginx)
    return response


async def _delete_after(conversation: Conversation, message: Message) -> None:
    await conversation.messages.filter(
        Q(created_at__gt=message.created_at) | Q(created_at=message.created_at, id__gt=message.pk)
    ).adelete()


@require_POST
async def send_message(request, conversation_id: int):
    prepared, error = await _prepare(request, conversation_id)
    if error:
        return error
    user, conversation, spec, data = prepared
    content = _validate_content(data)
    if isinstance(content, JsonResponse):
        return content
    message = await Message.objects.acreate(conversation=conversation, role=Message.Role.USER, content=content)
    if conversation.title == DEFAULT_TITLE:
        conversation.title = title_from(content)
        await conversation.asave(update_fields=["title", "updated_at"])
    return _stream(user, conversation, spec, {"id": message.pk, "content": content, "title": conversation.title})


@require_POST
async def regenerate(request, conversation_id: int):
    """Replace the reply to the last user message (also used to retry a failed reply)."""
    prepared, error = await _prepare(request, conversation_id)
    if error:
        return error
    user, conversation, spec, _ = prepared
    last_user = await conversation.messages.filter(role=Message.Role.USER).order_by("-created_at", "-id").afirst()
    if last_user is None:
        return _error(400, "There is no message to regenerate a reply for.")
    await _delete_after(conversation, last_user)
    return _stream(user, conversation, spec)


@require_POST
async def edit_message(request, conversation_id: int, message_id: int):
    """Edit a user message, discard everything after it, and generate a new reply."""
    prepared, error = await _prepare(request, conversation_id)
    if error:
        return error
    user, conversation, spec, data = prepared
    content = _validate_content(data)
    if isinstance(content, JsonResponse):
        return content
    message = await conversation.messages.filter(pk=message_id, role=Message.Role.USER).afirst()
    if message is None:
        return _error(404, "Message not found.")
    message.content = content
    await message.asave(update_fields=["content"])
    await _delete_after(conversation, message)
    return _stream(user, conversation, spec, {"id": message.pk, "content": content, "title": conversation.title})
