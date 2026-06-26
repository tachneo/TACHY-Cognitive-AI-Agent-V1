"""SQLAlchemy models + session factory.

Mirrors app/db/schema.sql. The CognitiveMemory model is the core store; other
tables are added as their phases land.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Integer, String, Text, create_engine, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


class CognitiveMemory(Base):
    __tablename__ = "cognitive_memories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
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


_engine = None
SessionLocal: sessionmaker | None = None


def init_engine():
    """Lazily build the engine/session factory from settings."""
    global _engine, SessionLocal
    if _engine is None:
        _engine = create_engine(get_settings().db_url, pool_pre_ping=True, future=True)
        SessionLocal = sessionmaker(bind=_engine, autoflush=False, future=True)
    return _engine
