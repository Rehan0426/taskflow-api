"""Integration tests for registration, login rate limit, refresh rotation, reuse detection, and logout."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, RefreshToken
from tests.conftest import auth_headers, register_and_login


def test_register_normalizes_email_and_blocks_duplicates(client: TestClient) -> None:
    res = client.post(
        "/auth/register",
        json={
            "email": "  Alice.Smith@Example.COM ",
            "full_name": "Alice Smith",
            "password": "SecurePassword1!",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["email"] == "alice.smith@example.com"
    assert "hashed_password" not in data

    dup = client.post(
        "/auth/register",
        json={
            "email": "alice.smith@example.com",
            "full_name": "Alice Duplicate",
            "password": "SecurePassword1!",
        },
    )
    assert dup.status_code == 409
    assert dup.json()["code"] == "CONFLICT"


def test_login_generic_error_and_rate_limiting(client: TestClient, db_session: Session) -> None:
    register_and_login(client, "bob@example.com", "CorrectPass1!")

    # 5 failed login attempts allowed before rate limit blocks the 6th
    for _ in range(5):
        fail_res = client.post(
            "/auth/login",
            json={"email": "bob@example.com", "password": "WrongPassword1!"},
        )
        assert fail_res.status_code == 401
        assert fail_res.json()["message"] == "Invalid email or password"

    sixth = client.post(
        "/auth/login",
        json={"email": "bob@example.com", "password": "WrongPassword1!"},
    )
    assert sixth.status_code == 429
    assert "Retry-After" in sixth.headers
    assert sixth.json()["code"] == "RATE_LIMITED"

    # Verify audit logs recorded login failures
    failures = list(
        db_session.scalars(select(AuditLog).where(AuditLog.action == "auth.login_failure")).all()
    )
    assert len(failures) == 5


def test_refresh_token_rotation_and_reuse_detection(
    client: TestClient, db_session: Session
) -> None:
    user_ctx = register_and_login(client, "rotate@example.com")
    refresh_1 = str(user_ctx["refresh_token"])

    # First rotation succeeds and returns a new token pair
    rot_res = client.post("/auth/refresh", json={"refresh_token": refresh_1})
    assert rot_res.status_code == 200
    refresh_2 = rot_res.json()["refresh_token"]
    assert refresh_2 != refresh_1

    # Reusing refresh_1 must trigger reuse detection and revoke the entire token family (including refresh_2)
    reuse_res = client.post("/auth/refresh", json={"refresh_token": refresh_1})
    assert reuse_res.status_code == 401
    assert "reuse detected" in reuse_res.json()["message"].lower()

    # Now refresh_2 is also revoked because it belongs to the compromised family
    subsequent_res = client.post("/auth/refresh", json={"refresh_token": refresh_2})
    assert subsequent_res.status_code == 401

    # Confirm all tokens in DB for this user are revoked and audit log was created
    tokens = list(
        db_session.scalars(
            select(RefreshToken).where(RefreshToken.user_id == int(user_ctx["user_id"]))
        ).all()
    )
    assert all(t.revoked for t in tokens)

    reuse_logs = list(
        db_session.scalars(
            select(AuditLog).where(AuditLog.action == "auth.token_reuse_detected")
        ).all()
    )
    assert len(reuse_logs) == 2


def test_logout_revokes_refresh_token_and_users_me(client: TestClient) -> None:
    user_ctx = register_and_login(client, "me@example.com")
    access = str(user_ctx["access_token"])
    refresh = str(user_ctx["refresh_token"])

    me_res = client.get("/users/me", headers=auth_headers(access))
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "me@example.com"

    logout_res = client.post("/auth/logout", json={"refresh_token": refresh})
    assert logout_res.status_code == 204

    after_logout = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert after_logout.status_code == 401
