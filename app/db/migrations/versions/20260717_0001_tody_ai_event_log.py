"""Durable sanitized TODY AI event and attachment state logs.

Revision ID: 20260717_0001
Revises: 20260710_0002
Create Date: 2026-07-17

These tables preserve learning/debugging evidence for TODY chat automation
without storing raw secrets or full chat bodies.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260717_0001"
down_revision = "20260710_0002"
branch_labels = None
depends_on = None


def _big_id() -> sa.BigInteger:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "tody_ai_event_logs",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=True),
        sa.Column("message_id", sa.String(120), nullable=True),
        sa.Column("direction", sa.String(32), nullable=True),
        sa.Column("actor", sa.String(64), nullable=False, server_default="system"),
        sa.Column("status", sa.String(32), nullable=False, server_default="observed"),
        sa.Column("body_hash", sa.String(128), nullable=True),
        sa.Column("body_preview", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_tody_ai_event_logs_event_type", "tody_ai_event_logs", ["event_type"])
    op.create_index(
        "ix_tody_ai_event_logs_conversation_id",
        "tody_ai_event_logs",
        ["conversation_id"],
    )
    op.create_index("ix_tody_ai_event_logs_message_id", "tody_ai_event_logs", ["message_id"])
    op.create_index("ix_tody_ai_event_logs_status", "tody_ai_event_logs", ["status"])

    op.create_table(
        "tody_attachment_states",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column("conversation_id", sa.BigInteger(), nullable=True),
        sa.Column("message_id", sa.String(120), nullable=True),
        sa.Column("attachment_id", sa.String(120), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="observed"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(255), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "conversation_id",
            "message_id",
            "attachment_id",
            name="uq_tody_attachment_state_source",
        ),
        sa.CheckConstraint("retry_count >= 0", name="ck_tody_attachment_retry_count"),
    )
    op.create_index(
        "ix_tody_attachment_states_conversation_id",
        "tody_attachment_states",
        ["conversation_id"],
    )
    op.create_index(
        "ix_tody_attachment_states_message_id",
        "tody_attachment_states",
        ["message_id"],
    )
    op.create_index(
        "ix_tody_attachment_states_attachment_id",
        "tody_attachment_states",
        ["attachment_id"],
    )
    op.create_index("ix_tody_attachment_states_status", "tody_attachment_states", ["status"])


def downgrade() -> None:
    op.drop_index("ix_tody_attachment_states_status", table_name="tody_attachment_states")
    op.drop_index(
        "ix_tody_attachment_states_attachment_id",
        table_name="tody_attachment_states",
    )
    op.drop_index("ix_tody_attachment_states_message_id", table_name="tody_attachment_states")
    op.drop_index(
        "ix_tody_attachment_states_conversation_id",
        table_name="tody_attachment_states",
    )
    op.drop_table("tody_attachment_states")

    op.drop_index("ix_tody_ai_event_logs_status", table_name="tody_ai_event_logs")
    op.drop_index("ix_tody_ai_event_logs_message_id", table_name="tody_ai_event_logs")
    op.drop_index(
        "ix_tody_ai_event_logs_conversation_id",
        table_name="tody_ai_event_logs",
    )
    op.drop_index("ix_tody_ai_event_logs_event_type", table_name="tody_ai_event_logs")
    op.drop_table("tody_ai_event_logs")
