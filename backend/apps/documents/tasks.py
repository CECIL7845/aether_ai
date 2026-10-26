import logging

from django.db import transaction
from django.tasks import task

from apps.providers.base import ProviderError
from apps.providers.embeddings import get_embedder
from apps.usage.models import UsageRecord

from .chunking import chunk_segments
from .extract import ExtractionError, extract
from .models import Chunk, Document

logger = logging.getLogger(__name__)


@task
def process_document(document_id: int) -> None:
    """Extract → chunk → embed → store. Always leaves the document in `ready` or `failed` with a reason."""
    document = Document.objects.filter(pk=document_id).first()
    if document is None or document.status not in (Document.Status.QUEUED, Document.Status.PROCESSING):
        return
    document.status = Document.Status.PROCESSING
    document.save(update_fields=["status", "updated_at"])
    try:
        with document.file.open("rb") as f:
            data = f.read()
        extracted = extract(document.kind, data)
        drafts = chunk_segments(extracted.segments)

        vectors: list[list[float]] | None = None
        embedding_model = ""
        embedder = get_embedder()
        if embedder is not None:
            try:
                vectors = embedder.embed([d.text for d in drafts], "document")
                embedding_model = embedder.model
                UsageRecord.objects.create(
                    user_id=document.user_id, provider="embedding", model_id=embedder.model,
                    input_tokens=sum(len(d.text) for d in drafts) // 4, output_tokens=0, estimated=True,
                )
            except ProviderError as e:
                # Keep the document usable with keyword search rather than failing the upload.
                logger.warning("embedding failed for document %s: %s", document_id, e)
                vectors = None

        with transaction.atomic():
            document.chunks.all().delete()
            Chunk.objects.bulk_create(
                Chunk(
                    document=document, user_id=document.user_id, index=i, text=d.text, page_start=d.page_start,
                    page_end=d.page_end, location=d.location, embedding=vectors[i] if vectors else None,
                )
                for i, d in enumerate(drafts)
            )
            document.status = Document.Status.READY
            document.error = ""
            document.page_count = extracted.page_count
            document.char_count = extracted.char_count
            document.chunk_count = len(drafts)
            document.embedding_model = embedding_model
            document.save()
    except ExtractionError as e:
        _fail(document, str(e))
    except Exception:
        logger.exception("processing failed for document %s", document_id)
        _fail(document, "Processing failed unexpectedly. Try uploading the file again.")


def _fail(document: Document, reason: str) -> None:
    document.status = Document.Status.FAILED
    document.error = reason[:500]
    document.save(update_fields=["status", "error", "updated_at"])
