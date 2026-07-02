"""Phase 0.2 — deployment files, schema alignment, and broader audit."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_deployment_foundation_files_exist():
    expected = [
        "Dockerfile",
        ".dockerignore",
        "DEPLOYMENT.md",
        "alembic.ini",
        "app/db/migrations/env.py",
        "app/db/migrations/script.py.mako",
        "app/db/migrations/versions/20260627_0001_initial_schema.py",
    ]

    missing = [path for path in expected if not (ROOT / path).exists()]
    assert missing == []


def test_orm_metadata_covers_bootstrap_schema_tables():
    from app.db.models import Base

    expected_tables = {
        "cognitive_memories",
        "cognitive_decisions",
        "cognitive_interests",
        "cognitive_behavior_patterns",
        "cognitive_goals",
        "cognitive_risks",
        "cognitive_approvals",
        "cognitive_audit_logs",
        "cognitive_skills",
        "cognitive_reflections",
    }

    assert expected_tables <= set(Base.metadata.tables)


def test_init_db_creates_all_schema_tables():
    from sqlalchemy import inspect

    from app.db import models

    engine = models.init_engine()
    tables = set(inspect(engine).get_table_names())

    assert {
        "cognitive_memories",
        "cognitive_decisions",
        "cognitive_interests",
        "cognitive_behavior_patterns",
        "cognitive_goals",
        "cognitive_risks",
        "cognitive_approvals",
        "cognitive_audit_logs",
        "cognitive_skills",
        "cognitive_reflections",
    } <= tables


def test_memory_route_writes_audit_event():
    from sqlalchemy import select

    from app.api.routes_memory import MemoryIn, add_memory
    from app.db.models import CognitiveAuditLog, session_scope

    out = add_memory(MemoryIn(title="Deployment note", content="Docker added"))
    assert out["saved"] is True

    with session_scope() as s:
        actions = [
            row.action
            for row in s.scalars(
                select(CognitiveAuditLog).order_by(CognitiveAuditLog.id)
            ).all()
        ]

    assert "memory_added" in actions


def test_decision_route_writes_audit_event():
    from sqlalchemy import select

    from app.api.routes_decision import DecisionIn, evaluate
    from app.db.models import CognitiveAuditLog, session_scope

    out = evaluate(DecisionIn(message="Please deploy to production"))
    assert out["requires_approval"] is True

    with session_scope() as s:
        actions = [
            row.action
            for row in s.scalars(
                select(CognitiveAuditLog).order_by(CognitiveAuditLog.id)
            ).all()
        ]

    assert "decision_evaluated" in actions
