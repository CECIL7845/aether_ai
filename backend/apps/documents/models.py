import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.db import models
from pgvector.django import HnswIndex, VectorField


def upload_path(instance, filename):
    # Random, non-guessable storage name; the original name is kept only in `title`.
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"documents/{instance.user_id}/{uuid.uuid4().hex}.{ext}"


class Document(models.Model):
    class Kind(models.TextChoices):
        PDF = "pdf"
        DOCX = "docx"
        TEXT = "text"
        CSV = "csv"
        XLSX = "xlsx"

    class Status(models.TextChoices):
        QUEUED = "queued"
        PROCESSING = "processing"
        READY = "ready"
        FAILED = "failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to=upload_path, max_length=300)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    error = models.CharField(max_length=500, blank=True)
    page_count = models.PositiveIntegerField(null=True, blank=True)
    char_count = models.PositiveIntegerField(default=0)
    chunk_count = models.PositiveIntegerField(default=0)
    # Empty when chunks were indexed for keyword search only (no embedding provider configured or it failed).
    embedding_model = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self):
        return self.title


class Chunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    # Denormalised owner so every retrieval query can filter by user directly (defence against cross-user leaks).
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    index = models.PositiveIntegerField()
    text = models.TextField()
    page_start = models.PositiveIntegerField(null=True, blank=True)
    page_end = models.PositiveIntegerField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)  # human-readable, e.g. "Page 3" or "Sheet1, rows 2–51"
    embedding = VectorField(dimensions=settings.EMBEDDING_DIMENSIONS, null=True, blank=True)
    search = models.GeneratedField(
        expression=SearchVector("text", config="english"),
        output_field=SearchVectorField(),
        db_persist=True,
    )

    class Meta:
        ordering = ["document", "index"]
        indexes = [
            GinIndex(fields=["search"]),
            HnswIndex(name="chunk_embedding_hnsw", fields=["embedding"], m=16, ef_construction=64,
                      opclasses=["vector_cosine_ops"]),
            models.Index(fields=["user", "document"]),
        ]
