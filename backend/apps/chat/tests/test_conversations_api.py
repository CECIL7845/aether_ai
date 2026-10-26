import pytest

from apps.accounts.models import User
from apps.chat.models import Conversation, Message

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user("ama@example.com", "correct-horse-battery-9")


@pytest.fixture
def client(api, user):
    api.force_authenticate(user)
    return api


def test_create_list_rename_archive_delete(client, user, scripted):
    created = client.post("/api/conversations/", {}).json()
    assert created["title"] == "New conversation"

    r = client.patch(f"/api/conversations/{created['id']}/", {"title": "  Budget   review "})
    assert r.json()["title"] == "Budget review"
    assert client.patch(f"/api/conversations/{created['id']}/", {"title": "   "}).status_code == 400

    client.patch(f"/api/conversations/{created['id']}/", {"archived": True})
    assert client.get("/api/conversations/?archived=false").json()["count"] == 0
    assert client.get("/api/conversations/?archived=true").json()["count"] == 1

    assert client.delete(f"/api/conversations/{created['id']}/").status_code == 204
    assert not Conversation.objects.filter(pk=created["id"]).exists()


def test_cannot_set_unavailable_model(client, scripted):
    created = client.post("/api/conversations/", {}).json()
    r = client.patch(f"/api/conversations/{created['id']}/", {"model_id": "claude-opus-5-5"})
    assert r.status_code == 400  # no Anthropic key configured in this test
    assert client.patch(f"/api/conversations/{created['id']}/", {"model_id": "scripted-model"}).status_code == 200


def test_retrieve_includes_messages_and_search_matches_content(client, user):
    conv = Conversation.objects.create(user=user, title="Untitled")
    Message.objects.create(conversation=conv, role="user", content="How do pgvector indexes work?")
    detail = client.get(f"/api/conversations/{conv.pk}/").json()
    assert [m["content"] for m in detail["messages"]] == ["How do pgvector indexes work?"]
    assert client.get("/api/conversations/?q=PGVECTOR").json()["count"] == 1
    assert client.get("/api/conversations/?q=kubernetes").json()["count"] == 0


def test_export_markdown_and_text(client, user):
    conv = Conversation.objects.create(user=user, title="Trip plan")
    Message.objects.create(conversation=conv, role="user", content="Plan a trip to Kumasi")
    Message.objects.create(conversation=conv, role="assistant", content="Day 1: Manhyia Palace", model_id="m1")
    Message.objects.create(conversation=conv, role="assistant", content="partial", status="error")

    md = client.get(f"/api/conversations/{conv.pk}/export/?fmt=md")
    assert md["Content-Disposition"] == 'attachment; filename="trip-plan.md"'
    body = md.content.decode()
    assert "# Trip plan" in body and "## You" in body and "Day 1: Manhyia Palace" in body
    assert "partial" not in body  # failed replies are excluded

    txt = client.get(f"/api/conversations/{conv.pk}/export/?fmt=txt")
    assert txt["Content-Type"].startswith("text/plain")
    assert client.get(f"/api/conversations/{conv.pk}/export/?fmt=exe").status_code == 400


def test_models_endpoint_reports_availability(client, scripted):
    data = client.get("/api/models/").json()
    assert data["default"] == "scripted-model"
    by_id = {m["id"]: m for m in data["models"]}
    assert by_id["scripted-model"]["available"] is True
    assert by_id["claude-opus-5-5"]["available"] is False
    assert by_id["claude-opus-5-5"]["input_price_per_mtok"] == "4.00"
    assert by_id["gemini-3.5-flash"]["input_price_per_mtok"] is None  # unverified price is not invented


def test_usage_endpoint(client):
    data = client.get("/api/usage/me/").json()
    assert data["allowed"] is True
    assert data["tokens_last_24h"] == 0


def test_conversation_endpoints_require_auth(api):
    assert api.get("/api/conversations/").status_code == 403
    assert api.get("/api/models/").status_code == 403
