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
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer,
    Numeric, String, Text, UniqueConstraint, create_engine, func,
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


# ── Self-module control plane (Phase 1) ──────────────────────────

_MODULE_TYPES = (
    "emotion", "memory", "reasoning", "speech", "tool", "agent", "evaluator",
    "safety_helper", "business", "erp", "tody", "curriculum", "self_model", "other",
)
_RISK_LEVELS = ("low", "medium", "high", "critical")
_JSON_DEFAULT = "[]"


class SelfModuleProposal(Base):
    __tablename__ = "self_module_proposals"
    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    module_key: Mapped[str] = mapped_column(String(120), index=True)
    module_name: Mapped[str] = mapped_column(String(180))
    module_type: Mapped[str] = mapped_column(String(80))
    purpose: Mapped[str] = mapped_column(Text)
    weakness_detected: Mapped[str] = mapped_column(Text)
    expected_improvement: Mapped[str] = mapped_column(Text)
    proposed_by: Mapped[str] = mapped_column(String(50))
    risk_level: Mapped[str] = mapped_column(String(50))
    allowed_actions_json: Mapped[str] = mapped_column(Text, default=_JSON_DEFAULT)
    blocked_actions_json: Mapped[str] = mapped_column(Text, default=_JSON_DEFAULT)
    required_tests_json: Mapped[str] = mapped_column(Text, default=_JSON_DEFAULT)
    fallback_module_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    rollback_plan: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(80), default="draft", index=True)
    evaluation_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    validation_report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_counter: Mapped[int] = mapped_column(Integer, default=1)
    approval_request_id: Mapped[int | None] = mapped_column(
        _BIGID, ForeignKey("cognitive_approvals.id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        CheckConstraint(f"module_type IN { _MODULE_TYPES!r}".replace("'", "'"), name="ck_self_module_proposals_module_type"),
        CheckConstraint("proposed_by IN ('shree','rohit','system')", name="ck_self_module_proposals_proposed_by"),
        CheckConstraint("risk_level IN ('low','medium','high','critical')", name="ck_self_module_proposals_risk_level"),
        CheckConstraint("status IN ('draft','spec_created','coded','tested','failed_validation','shadow','approval_pending','approved','canary_5','canary_25','active','rejected','rolled_back')", name="ck_self_module_proposals_status"),
        CheckConstraint("evaluation_score IS NULL OR (evaluation_score >= 0 AND evaluation_score <= 100)", name="ck_self_module_proposals_evaluation_score"),
        CheckConstraint("version_counter >= 1", name="ck_self_module_proposals_version_counter"),
    )


class SelfModule(Base):
    __tablename__ = "self_modules"
    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    module_key: Mapped[str] = mapped_column(String(120), unique=True)
    module_name: Mapped[str] = mapped_column(String(180))
    module_type: Mapped[str] = mapped_column(String(80))
    version: Mapped[str] = mapped_column(String(50), default="0.1.0")
    active_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(80), default="inactive", index=True)
    sandbox_path: Mapped[str] = mapped_column(Text)
    live_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    allowed_actions_json: Mapped[str] = mapped_column(Text, default=_JSON_DEFAULT)
    blocked_actions_json: Mapped[str] = mapped_column(Text, default=_JSON_DEFAULT)
    health_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    last_eval_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    fallback_module_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by: Mapped[str] = mapped_column(String(50), default="system")
    version_counter: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        CheckConstraint("module_type IN ('emotion','memory','reasoning','speech','tool','agent','evaluator','safety_helper','business','erp','tody','curriculum','self_model','other')", name="ck_self_modules_module_type"),
        CheckConstraint("status IN ('inactive','shadow','canary_5','canary_25','active','failed','rollback','disabled')", name="ck_self_modules_status"),
        CheckConstraint("health_score IS NULL OR (health_score >= 0 AND health_score <= 100)", name="ck_self_modules_health_score"),
        CheckConstraint("last_eval_score IS NULL OR (last_eval_score >= 0 AND last_eval_score <= 100)", name="ck_self_modules_eval_score"),
        CheckConstraint("version_counter >= 1", name="ck_self_modules_version_counter"),
    )


class ModuleVersion(Base):
    __tablename__ = "module_versions"
    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    module_key: Mapped[str] = mapped_column(String(120), ForeignKey("self_modules.module_key"), index=True)
    version: Mapped[str] = mapped_column(String(50))
    code_hash: Mapped[str] = mapped_column(String(128))
    artifact_hash: Mapped[str] = mapped_column(String(128))
    spec_path: Mapped[str] = mapped_column(Text)
    sandbox_path: Mapped[str] = mapped_column(Text)
    test_path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(80), default="draft", index=True)
    evaluation_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    validation_report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    __table_args__ = (
        UniqueConstraint("module_key", "version", name="uq_module_versions_key_version"),
        CheckConstraint("status IN ('draft','testing','passed','failed','shadow','canary','active','archived')", name="ck_module_versions_status"),
        CheckConstraint("evaluation_score IS NULL OR (evaluation_score >= 0 AND evaluation_score <= 100)", name="ck_module_versions_score"),
    )


class ModuleCapabilityEnvelope(Base):
    __tablename__ = "module_capability_envelopes"
    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    module_key: Mapped[str] = mapped_column(String(120), ForeignKey("self_modules.module_key"), index=True)
    version: Mapped[str] = mapped_column(String(50))
    risk_level: Mapped[str] = mapped_column(String(50))
    allowed_actions_json: Mapped[str] = mapped_column(Text, default=_JSON_DEFAULT)
    blocked_actions_json: Mapped[str] = mapped_column(Text, default=_JSON_DEFAULT)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    filesystem_scope_json: Mapped[str] = mapped_column(Text, default=_JSON_DEFAULT)
    network_scope_json: Mapped[str] = mapped_column(Text, default=_JSON_DEFAULT)
    data_scope_json: Mapped[str] = mapped_column(Text, default=_JSON_DEFAULT)
    approval_request_id: Mapped[int | None] = mapped_column(
        _BIGID, ForeignKey("cognitive_approvals.id", ondelete="SET NULL"), nullable=True
    )
    policy_hash: Mapped[str] = mapped_column(String(128))
    policy_snapshot_hash: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_by: Mapped[str] = mapped_column(String(50))
    valid_from: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    version_counter: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        UniqueConstraint("module_key", "version", "policy_snapshot_hash", name="uq_module_capability_policy"),
        CheckConstraint("risk_level IN ('low','medium','high','critical')", name="ck_module_capability_risk"),
        CheckConstraint("status IN ('draft','active','expired','revoked')", name="ck_module_capability_status"),
        CheckConstraint("version_counter >= 1", name="ck_module_capability_version_counter"),
    )


class ModuleControlLog(Base):
    __tablename__ = "module_control_logs"
    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    module_key: Mapped[str] = mapped_column(String(120), ForeignKey("self_modules.module_key"), index=True)
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    action: Mapped[str] = mapped_column(String(120))
    old_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    new_status: Mapped[str] = mapped_column(String(80))
    reason: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())


class SurgerySession(Base):
    __tablename__ = "surgery_sessions"
    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    module_key: Mapped[str] = mapped_column(String(120), ForeignKey("self_modules.module_key"), index=True)
    from_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    to_version: Mapped[str] = mapped_column(String(50))
    surgery_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(80), default="planned", index=True)
    reason: Mapped[str] = mapped_column(Text)
    validation_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    health_before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    health_after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    rollback_plan: Mapped[str] = mapped_column(Text)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(String(50))
    policy_snapshot_hash: Mapped[str] = mapped_column(String(128))
    version_counter: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        CheckConstraint("surgery_type IN ('create','upgrade','patch','rollback','disable')", name="ck_surgery_type"),
        CheckConstraint("status IN ('planned','isolated','testing','shadow','canary_5','canary_25','promoted','rolled_back','failed')", name="ck_surgery_status"),
        CheckConstraint("validation_score IS NULL OR (validation_score >= 0 AND validation_score <= 100)", name="ck_surgery_score"),
        CheckConstraint("version_counter >= 1", name="ck_surgery_version_counter"),
    )


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    eval_name: Mapped[str] = mapped_column(String(180))
    module_key: Mapped[str] = mapped_column(String(120), ForeignKey("self_modules.module_key"), index=True)
    version: Mapped[str] = mapped_column(String(50))
    score: Mapped[float] = mapped_column(Numeric(5, 2))
    passed: Mapped[bool] = mapped_column(Boolean)
    failures_json: Mapped[str] = mapped_column(Text, default=_JSON_DEFAULT)
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    __table_args__ = (CheckConstraint("score >= 0 AND score <= 100", name="ck_evaluation_runs_score"),)


class ModuleShadowRun(Base):
    __tablename__ = "module_shadow_runs"
    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    module_key: Mapped[str] = mapped_column(String(120), ForeignKey("self_modules.module_key"), index=True)
    version: Mapped[str] = mapped_column(String(50))
    input_hash: Mapped[str] = mapped_column(String(128))
    live_output_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    shadow_output_hash: Mapped[str] = mapped_column(String(128))
    score: Mapped[float] = mapped_column(Numeric(5, 2))
    diff_json: Mapped[str] = mapped_column(Text, default="{}")
    safety_flags_json: Mapped[str] = mapped_column(Text, default=_JSON_DEFAULT)
    latency_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100", name="ck_module_shadow_runs_score"),
        CheckConstraint("latency_ms >= 0", name="ck_module_shadow_runs_latency"),
    )


class ModuleHealthSample(Base):
    __tablename__ = "module_health_samples"
    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    module_key: Mapped[str] = mapped_column(String(120), ForeignKey("self_modules.module_key"), index=True)
    version: Mapped[str] = mapped_column(String(50))
    health_score: Mapped[float] = mapped_column(Numeric(5, 2))
    error_rate: Mapped[float] = mapped_column(Numeric(7, 4), default=0)
    latency_p95_ms: Mapped[int] = mapped_column(Integer, default=0)
    safety_violation_count: Mapped[int] = mapped_column(Integer, default=0)
    privacy_leak_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    output_quality_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    user_correction_severity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_injection_failures: Mapped[int] = mapped_column(Integer, default=0)
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    __table_args__ = (
        CheckConstraint("health_score >= 0 AND health_score <= 100", name="ck_module_health_score"),
        CheckConstraint("error_rate >= 0 AND error_rate <= 1", name="ck_module_health_error_rate"),
        CheckConstraint("latency_p95_ms >= 0", name="ck_module_health_latency"),
        CheckConstraint("safety_violation_count >= 0 AND prompt_injection_failures >= 0", name="ck_module_health_counts"),
        CheckConstraint("output_quality_score IS NULL OR (output_quality_score >= 0 AND output_quality_score <= 100)", name="ck_module_health_quality"),
    )


class ModuleRoute(Base):
    __tablename__ = "module_routes"
    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    module_key: Mapped[str] = mapped_column(String(120), ForeignKey("self_modules.module_key"), unique=True)
    version: Mapped[str] = mapped_column(String(50))
    previous_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    percentage: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="inactive")
    policy_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    policy_snapshot_hash: Mapped[str] = mapped_column(String(128))
    updated_by: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    version_counter: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        CheckConstraint("percentage IN (0,5,25,100)", name="ck_module_routes_percentage"),
        CheckConstraint("status IN ('inactive','shadow','canary_5','canary_25','active','quarantined')", name="ck_module_routes_status"),
        CheckConstraint("version_counter >= 1", name="ck_module_routes_version_counter"),
    )


class SelfModelEvent(Base):
    __tablename__ = "self_model_events"
    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    event: Mapped[str] = mapped_column(String(180))
    evidence: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Numeric(5, 2))
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    self_state_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    __table_args__ = (CheckConstraint("confidence >= 0 AND confidence <= 100", name="ck_self_model_events_confidence"),)


class IdentityReflectionLog(Base):
    __tablename__ = "identity_reflection_logs"
    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    self_state_json: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Numeric(5, 2))
    consistency_passed: Mapped[bool] = mapped_column(Boolean)
    review_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    __table_args__ = (CheckConstraint("confidence >= 0 AND confidence <= 100", name="ck_identity_reflection_confidence"),)


class CognitiveTaskContext(Base):
    __tablename__ = "cognitive_task_contexts"
    id: Mapped[int] = mapped_column(_BIGID, primary_key=True, autoincrement=True)
    task_key: Mapped[str] = mapped_column(String(120), unique=True)
    goal: Mapped[str] = mapped_column(Text)
    current_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="dormant", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=5)
    deadline: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    relevant_memory_refs_json: Mapped[str] = mapped_column(Text, default=_JSON_DEFAULT)
    selected_modules_json: Mapped[str] = mapped_column(Text, default=_JSON_DEFAULT)
    pending_commitments_json: Mapped[str] = mapped_column(Text, default=_JSON_DEFAULT)
    checkpoint_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_triggers_json: Mapped[str] = mapped_column(Text, default=_JSON_DEFAULT)
    affective_state_json: Mapped[str] = mapped_column(Text, default="{}")
    created_by: Mapped[str] = mapped_column(String(50))
    last_activated_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    version_counter: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        CheckConstraint("status IN ('active','paused','waiting','dormant','completed','cancelled')", name="ck_cognitive_task_status"),
        CheckConstraint("priority >= 1 AND priority <= 10", name="ck_cognitive_task_priority"),
        CheckConstraint("version_counter >= 1", name="ck_cognitive_task_version_counter"),
    )


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
