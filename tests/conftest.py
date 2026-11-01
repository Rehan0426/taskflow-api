"""Pytest fixtures: isolated SQLite test database, FastAPI dependency overrides, and user/token helpers."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.rate_limit import login_rate_limiter
from app.db.base import Base
from app.db.session import get_db
from app.main import app

TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(test_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:
    """Enable foreign key enforcement in SQLite so cascade rules are tested."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def reset_state() -> Generator[None, None, None]:
    """Create fresh database tables and clear rate limiter before each test."""
    Base.metadata.create_all(bind=test_engine)
    login_rate_limiter.clear_all()
    yield
    Base.metadata.drop_all(bind=test_engine)
    login_rate_limiter.clear_all()


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """Provide a direct SQLAlchemy session for test assertions."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Provide a FastAPI TestClient wired to the isolated test database."""

    def _override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def register_and_login(
    client: TestClient,
    email: str,
    password: str = "StrongPass1!",
    full_name: str = "Test User",
) -> dict[str, str | int]:
    """Helper to register a user, log in, and return user_id, access_token, and refresh_token."""
    reg = client.post(
        "/auth/register",
        json={"email": email, "full_name": full_name, "password": password},
    )
    assert reg.status_code == 201, reg.text
    user_id = reg.json()["id"]

    login_res = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert login_res.status_code == 200, login_res.text
    tokens = login_res.json()
    return {
        "user_id": user_id,
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
    }


def auth_headers(access_token: str) -> dict[str, str]:
    """Return Bearer authorization header dict."""
    return {"Authorization": f"Bearer {access_token}"}
