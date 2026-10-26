import hashlib
import os

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.http import FileResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from .extract import ExtractionError, check_signature, kind_for
from .models import Document
from .serializers import DocumentSerializer
from .tasks import process_document


def _safe_title(name: str) -> str:
    name = os.path.basename(name.replace("\\", "/")).strip()
    return "".join(ch for ch in name if ch.isprintable())[:255] or "document"


class DocumentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin,
                      viewsets.GenericViewSet):
    serializer_class = DocumentSerializer
    parser_classes = [MultiPartParser]

    def get_queryset(self):
        return Document.objects.filter(user=self.request.user)

    def create(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "Attach a file in the 'file' field."}, status=400)
        title = _safe_title(upload.name)
        max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
        if upload.size > max_bytes:
            return Response({"detail": f"Files can be at most {settings.MAX_UPLOAD_MB} MB."}, status=400)
        if upload.size == 0:
            return Response({"detail": "The file is empty."}, status=400)

        mine = Document.objects.filter(user=request.user)
        if mine.count() >= settings.MAX_DOCUMENTS_PER_USER:
            return Response({"detail": "You have reached the maximum number of documents. Delete some first."},
                            status=400)
        used = mine.aggregate(total=Sum("size"))["total"] or 0
        if used + upload.size > settings.MAX_STORAGE_MB_PER_USER * 1024 * 1024:
            return Response({"detail": "This upload would exceed your storage limit."}, status=400)

        try:
            kind = kind_for(title)
            head = upload.read(8)
            upload.seek(0)
            check_signature(kind, head)
        except ExtractionError as e:
            return Response({"detail": str(e)}, status=400)

        digest = hashlib.sha256()
        for chunk in upload.chunks():
            digest.update(chunk)
        upload.seek(0)

        document = Document.objects.create(
            user=request.user, title=title, file=upload, kind=kind, size=upload.size, sha256=digest.hexdigest()
        )
        transaction.on_commit(lambda: process_document.enqueue(document.pk))
        return Response(DocumentSerializer(document).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        # Remove the stored file as well as the database rows (chunks cascade).
        storage, name = instance.file.storage, instance.file.name
        instance.delete()
        if name:
            storage.delete(name)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        document = self.get_object()
        response = FileResponse(document.file.open("rb"), as_attachment=True, filename=document.title,
                                content_type="application/octet-stream")
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @action(detail=True, methods=["post"])
    def reprocess(self, request, pk=None):
        document = self.get_object()
        if document.status == Document.Status.PROCESSING:
            return Response({"detail": "This document is already being processed."}, status=409)
        document.status = Document.Status.QUEUED
        document.error = ""
        document.save(update_fields=["status", "error", "updated_at"])
        transaction.on_commit(lambda: process_document.enqueue(document.pk))
        return Response(DocumentSerializer(document).data)
