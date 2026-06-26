"""SQLAlchemy models + session factory.

Mirrors app/db/schema.sql. The CognitiveMemory model is the core store; other
tables are added as their phases land.
"""
from __future__ import annotations

import datetime as dt
import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Integer, String, Text, create_engine, func,
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, Session, mapped_column, sessionmaker,
)

from app.config import get_settings


class Base(DeclarativeBase):
    pass


class CognitiveMemory(Base):
    __tablename__ = "cognitive_memories"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True, autoincrement=True,
    )
    memory_type: Mapped[str] = mapped_column(String(20))
    project: Mapped[str] = mapped_column(String(32), default="GENERAL")
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)

    importance_score: Mapped[int] = mapped_column(Integer, default=5)
    urgency_score: Mapped[int] = mapped_column(Integer, default=5)
    emotional_weight: Mapped[int] = mapped_column(Integer, default=5)
    risk_score: Mapped[int] = mapped_column(Integer, default=5)
    business_value_score: Mapped[int] = mapped_column(Integer, default=5)
    interest_score: Mapped[int] = mapped_column(Integer, default=5)

    emotion_tag: Mapped[str] = mapped_column(String(20), default="neutral")
    decision_status: Mapped[str] = mapped_column(String(20), default="not_decision")
    source_type: Mapped[str] = mapped_column(String(20), default="chat")

    related_person: Mapped[str | None] = mapped_column(String(255), nullable=True)
    related_client: Mapped[str | None] = mapped_column(String(255), nullable=True)
    related_module: Mapped[str | None] = mapped_column(String(255), nullable=True)

    lesson_learned: Mapped[str | None] = mapped_column(Text, nullable=True)
    future_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    avoid_action: Mapped[str | None] = mapped_column(Text, nullable=True)

    confidence_score: Mapped[int] = mapped_column(Integer, default=7)
    is_permanent: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


_BIGID = BigInteger().with_variant(Integer, "sqlite")


class CognitiveApproval(Base):
    """A high-risk action awaiting the guardian's decision."""
    __tablename__ = "cognitive_approvals"

    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(255))
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_tier: Mapped[str] = mapped_column(String(16), default="high")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    requested_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class CognitiveReflection(Base):
    """Output of the daily learning loop."""
    __tablename__ = "cognitive_reflections"

    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    lessons: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())


_engine = None
SessionLocal: sessionmaker | None = None


def init_engine():
    """Lazily build the engine/session factory from settings."""
    global _engine, SessionLocal
    if _engine is None:
        url = get_settings().db_url
        kwargs: dict = {"pool_pre_ping": True, "future": True}
        if url.startswith("sqlite"):
            # SQLite dev DB: ensure the storage dir exists, allow cross-thread use
            os.makedirs("storage", exist_ok=True)
            kwargs = {"future": True, "connect_args": {"check_same_thread": False}}
        _engine = create_engine(url, **kwargs)
        SessionLocal = sessionmaker(bind=_engine, autoflush=False, future=True)
    return _engine


def init_db() -> None:
    """Create tables if missing (SQLite dev / first run). Prod uses schema.sql."""
    engine = init_engine()
    Base.metadata.create_all(engine)


@contextmanager
def session_scope() -> Iterator["Session"]:
    """Transactional session: commit on success, rollback on error, always close."""
    init_engine()
    assert SessionLocal is not None
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
