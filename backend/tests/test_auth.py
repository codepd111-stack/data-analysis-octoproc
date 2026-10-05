import time

import pytest
from fastapi import HTTPException

from app.api import auth as auth_api
from app.core import auth as core_auth
from app.core.config import settings

CODE = "open-sesame"
SECRET = "x" * 32
LOGIN = "/api/auth/login"


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "access_code", CODE)
    monkeypatch.setattr(settings, "auth_secret", SECRET)
    auth_api._failures.clear()
    yield
    auth_api._failures.clear()


# ---------- tokens ----------


def test_token_round_trip(enabled):
    token, expires_at = core_auth.create_token()
    assert expires_at > time.time()
    assert core_auth.verify_token(token)


def test_tampered_tokens_are_rejected(enabled):
    token, _ = core_auth.create_token()
    payload, _, signature = token.partition(".")
    assert not core_auth.verify_token(f"{payload}.{'0' * len(signature)}")
    assert not core_auth.verify_token(f"{payload}x.{signature}")
    assert not core_auth.verify_token("garbage")
    assert not core_auth.verify_token("")


def test_expired_token_is_rejected(enabled, monkeypatch):
    monkeypatch.setattr(settings, "auth_token_days", -1)
    token, _ = core_auth.create_token()
    assert not core_auth.verify_token(token)


def test_token_signed_with_another_secret_is_rejected(enabled, monkeypatch):
    token, _ = core_auth.create_token()
    monkeypatch.setattr(settings, "auth_secret", "y" * 32)
    assert not core_auth.verify_token(token)


def test_require_auth_is_a_no_op_when_sign_in_is_off():
    assert settings.access_code == ""
    assert core_auth.require_auth(None) is None


def test_require_auth_wants_a_valid_bearer_token(enabled):
    token, _ = core_auth.create_token()
    for header in (None, "", "Bearer nope", f"Basic {token}", token):
        with pytest.raises(HTTPException) as exc:
            core_auth.require_auth(header)
        assert exc.value.status_code == 401
    assert core_auth.require_auth(f"Bearer {token}") is None


def test_startup_refuses_a_weak_secret(monkeypatch):
    monkeypatch.setattr(settings, "access_code", CODE)
    monkeypatch.setattr(settings, "auth_secret", "short")
    with pytest.raises(RuntimeError, match="AUTH_SECRET"):
        core_auth.validate_auth_config()


# ---------- /api/auth ----------


def test_status_reports_whether_sign_in_is_required(enabled, client):
    assert client.get("/api/auth/status").json() == {"authRequired": True}


def test_login_is_refused_when_sign_in_is_off(client):
    assert client.post(LOGIN, json={"code": "x"}).status_code == 400


def test_login_unlocks_protected_routes(enabled, client):
    assert client.get("/api/datasets").status_code == 401
    response = client.post(LOGIN, json={"code": CODE})
    assert response.status_code == 200
    token = response.json()["token"]
    assert client.get("/api/datasets", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_login_throttles_after_repeated_failures(enabled, client):
    for _ in range(auth_api.MAX_FAILURES):
        assert client.post(LOGIN, json={"code": "wrong"}).status_code == 401
    assert client.post(LOGIN, json={"code": "wrong"}).status_code == 429
    # Even the right code waits until the window passes
    assert client.post(LOGIN, json={"code": CODE}).status_code == 429


def test_forwarded_header_is_ignored_without_a_trusted_proxy(enabled, client):
    for i in range(auth_api.MAX_FAILURES):
        client.post(LOGIN, json={"code": "wrong"}, headers={"X-Forwarded-For": f"10.0.0.{i}"})
    # Every attempt came from the same real client: rotating the header must not reset the count
    response = client.post(LOGIN, json={"code": "wrong"}, headers={"X-Forwarded-For": "10.0.0.99"})
    assert response.status_code == 429


def test_forwarded_header_uses_the_proxy_appended_address(enabled, client, monkeypatch):
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    behind_proxy = {"X-Forwarded-For": "1.1.1.1, 9.9.9.9"}  # client-supplied, then proxy-appended
    for _ in range(auth_api.MAX_FAILURES):
        client.post(LOGIN, json={"code": "wrong"}, headers=behind_proxy)
    # Forging the left-hand part does not help: the right-hand address is the key
    spoofed = {"X-Forwarded-For": "2.2.2.2, 9.9.9.9"}
    assert client.post(LOGIN, json={"code": "wrong"}, headers=spoofed).status_code == 429
    # A different real client is counted separately
    other = {"X-Forwarded-For": "1.1.1.1, 8.8.8.8"}
    assert client.post(LOGIN, json={"code": "wrong"}, headers=other).status_code == 401


def test_stale_failure_records_are_pruned(enabled, monkeypatch):
    monkeypatch.setattr(auth_api, "PRUNE_ABOVE", 2)
    now = time.time()
    auth_api._failures["old"] = [now - auth_api.WINDOW_SECONDS - 1]
    auth_api._failures["recent"] = [now - 1]
    auth_api._prune_failures(now)
    assert set(auth_api._failures) == {"recent"}
