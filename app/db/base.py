"""SQLAlchemy 2.0 DeclarativeBase class.

Why this module exists:
SQLAlchemy 2.0 replaces the legacy `declarative_base()` function with a typed `DeclarativeBase`
subclass, enabling full static type checking (mypy/pyright/IDE autocomplete) with `Mapped[...]`
and `mapped_column(...)`.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
