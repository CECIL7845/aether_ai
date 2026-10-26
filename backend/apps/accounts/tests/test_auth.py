import pytest

from apps.accounts.models import User

pytestmark = pytest.mark.django_db
STRONG = "correct-horse-battery-9"


def test_register_logs_in_and_returns_user(csrf_api):
    r = csrf_api.post("/api/auth/register/", {"email": "Ama@Example.com", "password": STRONG})
    assert r.status_code == 201
    assert r.json()["email"] == "ama@example.com"
    assert "password" not in r.json()
    assert csrf_api.get("/api/auth/me/").status_code == 200


def test_password_is_hashed_with_argon2(csrf_api):
    csrf_api.post("/api/auth/register/", {"email": "a@example.com", "password": STRONG})
    assert User.objects.get(email="a@example.com").password.startswith("argon2")


def test_register_rejects_weak_password(csrf_api):
    r = csrf_api.post("/api/auth/register/", {"email": "a@example.com", "password": "12345678"})
    assert r.status_code == 400


def test_register_rejects_duplicate_email_case_insensitively(csrf_api):
    User.objects.create_user("kofi@example.com", STRONG)
    r = csrf_api.post("/api/auth/register/", {"email": "KOFI@example.com", "password": STRONG})
    assert r.status_code == 400


def test_login_failure_does_not_reveal_whether_email_exists(csrf_api):
    User.objects.create_user("kofi@example.com", STRONG)
    wrong_pw = csrf_api.post("/api/auth/login/", {"email": "kofi@example.com", "password": "nope-nope-1"})
    no_user = csrf_api.post("/api/auth/login/", {"email": "nobody@example.com", "password": "nope-nope-1"})
    assert wrong_pw.status_code == no_user.status_code == 400
    assert wrong_pw.json() == no_user.json()


def test_login_and_logout(csrf_api):
    User.objects.create_user("kofi@example.com", STRONG)
    r = csrf_api.post("/api/auth/login/", {"email": "kofi@example.com", "password": STRONG})
    assert r.status_code == 200
    csrf_api.credentials(HTTP_X_CSRFTOKEN=csrf_api.cookies["csrftoken"].value)  # token rotates on login
    assert csrf_api.post("/api/auth/logout/").status_code == 204
    assert csrf_api.get("/api/auth/me/").status_code == 403


def test_post_without_csrf_token_is_rejected(api):
    User.objects.create_user("kofi@example.com", STRONG)
    r = api.post("/api/auth/login/", {"email": "kofi@example.com", "password": STRONG})
    assert r.status_code == 403


def test_me_requires_authentication(api):
    assert api.get("/api/auth/me/").status_code == 403


def test_me_cannot_change_email(csrf_api):
    csrf_api.post("/api/auth/register/", {"email": "a@example.com", "password": STRONG})
    csrf_api.credentials(HTTP_X_CSRFTOKEN=csrf_api.cookies["csrftoken"].value)
    r = csrf_api.patch("/api/auth/me/", {"email": "evil@example.com", "display_name": "Ama"})
    assert r.status_code == 200
    assert r.json()["email"] == "a@example.com"
    assert r.json()["display_name"] == "Ama"


def test_login_is_rate_limited(csrf_api, settings):
    for _ in range(10):
        csrf_api.post("/api/auth/login/", {"email": "x@example.com", "password": "wrong-pass-1"})
    r = csrf_api.post("/api/auth/login/", {"email": "x@example.com", "password": "wrong-pass-1"})
    assert r.status_code == 429
