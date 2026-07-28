"""SQLAlchemy declarative base. No business-domain models in Phase 1."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Empty declarative metadata for Alembic and future models."""
