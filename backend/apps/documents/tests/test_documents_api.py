import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import User
from apps.documents.models import Chunk, Document
from apps.documents.retrieval import search

from .files import make_docx, make_pdf

pytestmark = pytest.mark.django_db


@pytest.fixture
def ama():
    return User.objects.create_user("ama@example.com", "correct-horse-battery-9")


@pytest.fixture
def kofi():
    return User.objects.create_user("kofi@example.com", "correct-horse-battery-9")


def client_for(api, user):
    api.force_authenticate(user)
    return api


def upload(client, name, data, capture):
    with capture(execute=True):
        return client.post("/api/documents/", {"file": SimpleUploadedFile(name, data)}, format="multipart")


def test_upload_processes_into_chunks_with_embeddings(api, ama, embedder, django_capture_on_commit_callbacks):
    c = client_for(api, ama)
    r = upload(c, "q3-report.pdf", make_pdf(["Accra revenue was 1.2 million cedis", "Kumasi opened in May"]),
               django_capture_on_commit_callbacks)
    assert r.status_code == 201, r.content
    doc = Document.objects.get(pk=r.json()["id"])
    assert doc.status == "ready" and doc.page_count == 2 and doc.chunk_count >= 1
    assert doc.embedding_model == "test-hashing-embedder"
    assert all(ch.embedding is not None for ch in doc.chunks.all())
    detail = c.get(f"/api/documents/{doc.pk}/").json()
    assert detail["status"] == "ready"


def test_failed_extraction_is_reported_not_hidden(api, ama, django_capture_on_commit_callbacks):
    c = client_for(api, ama)
    r = upload(c, "scan.pdf", make_pdf([""]), django_capture_on_commit_callbacks)
    doc = Document.objects.get(pk=r.json()["id"])
    assert doc.status == "failed" and "OCR" in doc.error and doc.chunk_count == 0


def test_upload_rejects_bad_files_before_storing(api, ama, settings, django_capture_on_commit_callbacks):
    c = client_for(api, ama)
    assert upload(c, "virus.exe", b"MZ...", django_capture_on_commit_callbacks).status_code == 400
    assert upload(c, "fake.pdf", b"MZ\x90\x00", django_capture_on_commit_callbacks).status_code == 400
    assert upload(c, "empty.txt", b"", django_capture_on_commit_callbacks).status_code == 400
    settings.MAX_UPLOAD_MB = 0
    assert upload(c, "a.txt", b"hello", django_capture_on_commit_callbacks).status_code == 400
    assert Document.objects.count() == 0


def test_storage_and_count_limits(api, ama, settings, django_capture_on_commit_callbacks):
    c = client_for(api, ama)
    settings.MAX_DOCUMENTS_PER_USER = 1
    assert upload(c, "a.txt", b"one", django_capture_on_commit_callbacks).status_code == 201
    r = upload(c, "b.txt", b"two", django_capture_on_commit_callbacks)
    assert r.status_code == 400 and "maximum number" in r.json()["detail"]


def test_path_traversal_in_filename_is_neutralised(api, ama, django_capture_on_commit_callbacks):
    c = client_for(api, ama)
    r = upload(c, "../../etc/passwd.txt", b"root:x:0:0", django_capture_on_commit_callbacks)
    doc = Document.objects.get(pk=r.json()["id"])
    assert doc.title == "passwd.txt"
    assert ".." not in doc.file.name and doc.file.name.startswith(f"documents/{ama.pk}/")


def test_users_cannot_access_each_others_documents(api, ama, kofi, embedder, django_capture_on_commit_callbacks):
    r = upload(client_for(api, ama), "secret.txt", b"The vault code is 4417.", django_capture_on_commit_callbacks)
    doc_id = r.json()["id"]
    c = client_for(api, kofi)
    assert c.get("/api/documents/").json()["count"] == 0
    assert c.get(f"/api/documents/{doc_id}/").status_code == 404
    assert c.get(f"/api/documents/{doc_id}/download/").status_code == 404
    assert c.delete(f"/api/documents/{doc_id}/").status_code == 404
    conv = c.post("/api/conversations/", {}, format="json").json()
    r = c.patch(f"/api/conversations/{conv['id']}/", {"document_ids": [doc_id]}, format="json")
    assert r.status_code == 400  # cannot attach someone else's document
    # Retrieval is scoped by owner even if another user's document id is passed in.
    assert search(kofi, [doc_id], "vault code") == []
    assert Document.objects.filter(pk=doc_id).exists()


def test_download_and_delete_remove_file_and_chunks(api, ama, django_capture_on_commit_callbacks):
    c = client_for(api, ama)
    data = make_docx("Notes", ["Meeting moved to Friday."])
    doc_id = upload(c, "notes.docx", data, django_capture_on_commit_callbacks).json()["id"]
    doc = Document.objects.get(pk=doc_id)
    dl = c.get(f"/api/documents/{doc_id}/download/")
    assert dl.status_code == 200 and b"".join(dl.streaming_content) == data
    assert dl["Content-Type"] == "application/octet-stream" and "attachment" in dl["Content-Disposition"]
    storage, name = doc.file.storage, doc.file.name
    assert storage.exists(name)
    assert c.delete(f"/api/documents/{doc_id}/").status_code == 204
    assert not storage.exists(name)
    assert Chunk.objects.filter(document_id=doc_id).count() == 0


TOPICS = [
    "Our refund policy allows returns within 30 days of purchase.",
    "Shipping to Tamale takes four working days by road.",
    "The Accra office is open from 8am to 5pm on weekdays.",
    "Staff receive 20 days of annual leave plus public holidays.",
    "Invoices are payable within 14 days by mobile money or bank transfer.",
    "The Kumasi warehouse stores cement, roofing sheets and paint.",
]


def make_indexed_document(user, embedder):
    doc = Document.objects.create(user=user, title="handbook.pdf", kind="pdf", size=1, sha256="x", status="ready",
                                  char_count=sum(map(len, TOPICS)))
    vectors = embedder.embed(TOPICS, "document") if embedder else [None] * len(TOPICS)
    Chunk.objects.bulk_create(
        Chunk(document=doc, user=user, index=i, text=t, page_start=i + 1, page_end=i + 1, location=f"Page {i + 1}",
              embedding=vectors[i])
        for i, t in enumerate(TOPICS)
    )
    return doc


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("how long does delivery to Tamale take?", "Tamale"),
        ("what time does the Accra office open", "8am"),
        ("which goods are stored in the warehouse", "cement"),
    ],
)
def test_hybrid_search_returns_the_relevant_chunk(ama, embedder, question, expected):
    # Paraphrase matching (no shared words) depends on real embeddings and is covered by the live Gemini test.
    doc = make_indexed_document(ama, embedder)
    [best] = search(ama, [doc.pk], question, k=1)
    assert expected.lower() in best.text.lower()
    assert best.ref == "S1"


def test_search_numbers_sources_in_document_order(ama, embedder):
    doc = make_indexed_document(ama, embedder)
    results = search(ama, [doc.pk], "Tamale shipping and Kumasi warehouse", k=2)
    assert [r.ref for r in results] == ["S1", "S2"]
    assert results[0].location == "Page 2" and results[1].location == "Page 6"


def test_vector_search_is_scoped_to_owner(ama, kofi, embedder):
    doc = make_indexed_document(ama, embedder)
    assert search(kofi, [doc.pk], "refund policy") == []


def test_keyword_only_mode_without_embeddings(api, ama, settings, django_capture_on_commit_callbacks):
    settings.EMBEDDING_PROVIDER = "none"
    c = client_for(api, ama)
    doc_id = upload(c, "faq.txt", b"Office hours are 8am to 5pm on weekdays.", django_capture_on_commit_callbacks
                    ).json()["id"]
    doc = Document.objects.get(pk=doc_id)
    assert doc.status == "ready" and doc.embedding_model == ""
    assert "Office hours" in search(ama, [doc_id], "office hours")[0].text
