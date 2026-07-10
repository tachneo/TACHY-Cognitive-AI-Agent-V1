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
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    requested_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    execution_started_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime, nullable=True,
    )
    execution_completed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime, nullable=True,
    )


class CognitiveDecision(Base):
    """Stored decision record for future explicit decision workflows."""
    __tablename__ = "cognitive_decisions"

    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255))
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    alternatives: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk: Mapped[str | None] = mapped_column(Text, nullable=True)
    chosen_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    project: Mapped[str] = mapped_column(String(64), default="GENERAL")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class CognitiveInterest(Base):
    """Persistent interest topic and score."""
    __tablename__ = "cognitive_interests"

    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    topic: Mapped[str] = mapped_column(String(255), unique=True)
    interest_score: Mapped[int] = mapped_column(Integer, default=5)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class CognitiveBehaviorPattern(Base):
    """Learned behavior/preference pattern."""
    __tablename__ = "cognitive_behavior_patterns"

    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    pattern: Mapped[str] = mapped_column(String(500))
    confidence_score: Mapped[int] = mapped_column(Integer, default=7)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())


class CognitiveGoal(Base):
    """Persistent goal for the goal system."""
    __tablename__ = "cognitive_goals"

    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255))
    horizon: Mapped[str] = mapped_column(String(16), default="short")
    status: Mapped[str] = mapped_column(String(16), default="open")
    project: Mapped[str] = mapped_column(String(64), default="GENERAL")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())


class CognitiveRisk(Base):
    """Persistent risk register entry."""
    __tablename__ = "cognitive_risks"

    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(32), default="production")
    severity: Mapped[int] = mapped_column(Integer, default=5)
    mitigation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())


class CognitiveReflection(Base):
    """Output of the daily learning loop."""
    __tablename__ = "cognitive_reflections"

    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    lessons: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())


class CognitiveAuditLog(Base):
    """Append-only safety and action audit record."""
    __tablename__ = "cognitive_audit_logs"

    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(64), default="system")
    action: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_tier: Mapped[str] = mapped_column(String(16), default="low")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())


class CognitiveSkill(Base):
    """Procedural checklist or reusable skill."""
    __tablename__ = "cognitive_skills"

    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    steps: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class CognitiveScheduledAction(Base):
    """A time-bound commitment extracted from chat and fired later (prospective
    memory). due_at is stored as UTC (naive); IST is resolved at extraction."""
    __tablename__ = "cognitive_scheduled_actions"

    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger)
    text: Mapped[str] = mapped_column(Text)
    due_at: Mapped[dt.datetime] = mapped_column(DateTime)
    source_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    person: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    actor: Mapped[str] = mapped_column(String(64), default="gemma-intent")
    approval_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    fired_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class CognitiveAutonomousTask(Base):
    """A recurring task Shree registers herself and the worker fires on her
    clock (the self-triggering loop). Handler is an allowlist key; next_run_at
    is UTC (naive)."""
    __tablename__ = "cognitive_autonomous_tasks"

    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    handler: Mapped[str] = mapped_column(String(32))
    intent: Mapped[str | None] = mapped_column(Text, nullable=True)
    params: Mapped[str | None] = mapped_column(Text, nullable=True)
    interval_minutes: Mapped[int] = mapped_column(Integer)
    at_time_hhmm: Mapped[str | None] = mapped_column(String(5), nullable=True)
    next_run_at: Mapped[dt.datetime] = mapped_column(DateTime)
    last_run_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    runs_today: Mapped[int] = mapped_column(Integer, default=0)
    run_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    total_runs: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_by: Mapped[str] = mapped_column(String(16), default="shree")
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class CognitiveRepairIntention(Base):
    """A recurring failure SIGNATURE Shree intends to repair — the metacognitive
    loop's memory of her own mistakes. Evidence-tiered: guardian corrections
    (tier 1) outrank conversational ground truth (2), hard system events (3),
    and LLM self-critique (4, hypothesis only). One row per signature; the row
    accumulates recurrence until its tier's threshold makes it repair-ready."""
    __tablename__ = "cognitive_repair_intentions"

    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    signature: Mapped[str] = mapped_column(String(160), unique=True)
    evidence_tier: Mapped[int] = mapped_column(Integer, default=4)  # best (lowest) seen
    fix_class: Mapped[str] = mapped_column(String(24), default="unknown")
    # memory | directive | config | code | capability | environment | unknown
    recurrence: Mapped[int] = mapped_column(Integer, default=1)
    guardian_involved: Mapped[bool] = mapped_column(Boolean, default=False)
    people: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    sample: Mapped[str | None] = mapped_column(Text, nullable=True)  # latest example
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="observing")
    # observing | ready | repairing | fixed | escalated | dismissed
    first_seen: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    repaired_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    repair_note: Mapped[str | None] = mapped_column(Text, nullable=True)


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
