"""Initial cognitive brain schema.

Revision ID: 20260627_0001
Revises: None
Create Date: 2026-06-27
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260627_0001"
down_revision = None
branch_labels = None
depends_on = None


def _big_id() -> sa.BigInteger:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "cognitive_memories",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column("memory_type", sa.String(20), nullable=False),
        sa.Column("project", sa.String(32), server_default="GENERAL"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("importance_score", sa.Integer(), server_default="5"),
        sa.Column("urgency_score", sa.Integer(), server_default="5"),
        sa.Column("emotional_weight", sa.Integer(), server_default="5"),
        sa.Column("risk_score", sa.Integer(), server_default="5"),
        sa.Column("business_value_score", sa.Integer(), server_default="5"),
        sa.Column("interest_score", sa.Integer(), server_default="5"),
        sa.Column("emotion_tag", sa.String(20), server_default="neutral"),
        sa.Column("decision_status", sa.String(20), server_default="not_decision"),
        sa.Column("source_type", sa.String(20), server_default="chat"),
        sa.Column("related_person", sa.String(255), nullable=True),
        sa.Column("related_client", sa.String(255), nullable=True),
        sa.Column("related_module", sa.String(255), nullable=True),
        sa.Column("lesson_learned", sa.Text(), nullable=True),
        sa.Column("future_action", sa.Text(), nullable=True),
        sa.Column("avoid_action", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Integer(), server_default="7"),
        sa.Column("is_permanent", sa.Boolean(), server_default=sa.false()),
        sa.Column("is_archived", sa.Boolean(), server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("idx_type", "cognitive_memories", ["memory_type"])
    op.create_index("idx_project", "cognitive_memories", ["project"])
    op.create_index("idx_emotion", "cognitive_memories", ["emotion_tag"])
    op.create_index("idx_permanent", "cognitive_memories", ["is_permanent"])

    op.create_table(
        "cognitive_decisions",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("alternatives", sa.Text(), nullable=True),
        sa.Column("risk", sa.Text(), nullable=True),
        sa.Column("chosen_action", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), server_default="pending"),
        sa.Column("project", sa.String(64), server_default="GENERAL"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "cognitive_interests",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column("topic", sa.String(255), nullable=False, unique=True),
        sa.Column("interest_score", sa.Integer(), server_default="5"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "cognitive_behavior_patterns",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column("pattern", sa.String(500), nullable=False),
        sa.Column("confidence_score", sa.Integer(), server_default="7"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "cognitive_goals",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("horizon", sa.String(16), server_default="short"),
        sa.Column("status", sa.String(16), server_default="open"),
        sa.Column("project", sa.String(64), server_default="GENERAL"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "cognitive_risks",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("category", sa.String(32), server_default="production"),
        sa.Column("severity", sa.Integer(), server_default="5"),
        sa.Column("mitigation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "cognitive_approvals",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column("action", sa.String(255), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("risk_tier", sa.String(16), server_default="high"),
        sa.Column("status", sa.String(16), server_default="pending"),
        sa.Column("requested_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "cognitive_audit_logs",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column("actor", sa.String(64), server_default="system"),
        sa.Column("action", sa.String(255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("risk_tier", sa.String(16), server_default="low"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "cognitive_skills",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("steps", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "cognitive_reflections",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("lessons", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    for table in (
        "cognitive_reflections",
        "cognitive_skills",
        "cognitive_audit_logs",
        "cognitive_approvals",
        "cognitive_risks",
        "cognitive_goals",
        "cognitive_behavior_patterns",
        "cognitive_interests",
        "cognitive_decisions",
        "cognitive_memories",
    ):
        op.drop_table(table)
