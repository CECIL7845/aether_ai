import pytest

pytestmark = pytest.mark.django_db


def test_health_reports_database_and_pgvector(api):
    r = api.get("/api/health/")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["pgvector"] != "missing"
