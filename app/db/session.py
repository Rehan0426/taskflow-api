"""Database engine and request-scoped session dependency.

Why this module exists:
Using a generator dependency (`get_db`) ensures every HTTP request gets its own isolated
SQLAlchemy `Session` that is automatically closed in the `finally` block—even if an unhandled
exception occurs mid-request. `pool_pre_ping=True` tests connections before checkout so stale
PostgreSQL connections after a database restart do not cause 500 errors.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=Session)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session per request and always close it afterward."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
