"""Durable, sanitized TODY event logging.

This module is deliberately best-effort: TODY chat handling must not fail just
because the evidence/audit DB is temporarily unavailable. Message bodies are
hashed and short-preview redacted; attachments are tracked by state, not by
persisting raw file bytes or private URLs.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from typing import Any

from sqlalchemy import select

from app.db.models import TodyAIEventLog, TodyAttachmentState, session_scope
from app.safety.audit_logger import log_event_safe


_MAX_PREVIEW = 240
_MAX_METADATA_VALUE = 500
_SECRET_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[^\s,;]+"),
    re.compile(r"(?i)\b(bearer|api[_-]?key|authorization|token|secret)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)\bnvapi-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{12,}"),
)
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+?\d[\s-]?){8,15}\b")


def _stable_hash(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def hash_value(value: Any) -> str | None:
    """Public helper for storing non-reversible hashes in metadata."""
    return _stable_hash(value)


def redact_text(value: Any, *, max_len: int = _MAX_PREVIEW) -> str | None:
    """Return a short redacted preview suitable for logs."""
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = _PHONE_RE.sub("[REDACTED_NUMBER]", text)
    if len(text) > max_len:
        text = text[: max_len - 3].rstrip() + "..."
    return text


def _clean_metadata(value: Any) -> Any:
    if value is None or isinstance(value, bool) or isinstance(value, int | float):
        return value
    if isinstance(value, str):
        return redact_text(value, max_len=_MAX_METADATA_VALUE)
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            key_s = str(key)[:80]
            if key_s.lower() in {"url", "uri", "href", "download_url", "token", "api_key"}:
                clean[key_s] = "[REDACTED]"
            else:
                clean[key_s] = _clean_metadata(item)
        return clean
    if isinstance(value, (list, tuple, set)):
        return [_clean_metadata(item) for item in list(value)[:20]]
    return redact_text(value, max_len=_MAX_METADATA_VALUE)


def _metadata_json(metadata: dict | None) -> str:
    try:
        return json.dumps(_clean_metadata(metadata or {}), ensure_ascii=True, sort_keys=True)
    except Exception:  # noqa: BLE001
        return "{}"


def record_event(
    event_type: str,
    *,
    conversation_id: int | None = None,
    message_id: int | str | None = None,
    direction: str | None = None,
    actor: str = "system",
    status: str = "observed",
    body: str | None = None,
    metadata: dict | None = None,
) -> int | None:
    """Persist a sanitized TODY event. Returns row id, or None on failure."""
    try:
        with session_scope() as s:
            row = TodyAIEventLog(
                event_type=(event_type or "unknown")[:80],
                conversation_id=conversation_id,
                message_id=str(message_id)[:120] if message_id is not None else None,
                direction=direction[:32] if direction else None,
                actor=(actor or "system")[:64],
                status=(status or "observed")[:32],
                body_hash=_stable_hash(body),
                body_preview=redact_text(body),
                metadata_json=_metadata_json(metadata),
            )
            s.add(row)
            s.flush()
            return int(row.id)
    except Exception as exc:  # noqa: BLE001
        log_event_safe(
            "tody_ai_event_log_failed",
            detail=f"event_type={event_type}; error={type(exc).__name__}",
            risk_tier="low",
        )
        return None


def _attachment_id(attachment: dict | None) -> str:
    data = attachment or {}
    for key in ("id", "attachment_id", "uuid", "file_id"):
        value = data.get(key)
        if value is not None:
            return str(value)[:120]
    fingerprint = json.dumps(_clean_metadata(data), ensure_ascii=True, sort_keys=True)
    return (_stable_hash(fingerprint) or "unknown")[:120]


def _attachment_size(attachment: dict | None) -> int | None:
    data = attachment or {}
    for key in ("size_bytes", "size", "file_size", "bytes"):
        value = data.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


def _attachment_metadata(attachment: dict | None, metadata: dict | None = None) -> dict:
    data = attachment or {}
    safe = {
        "name": data.get("name") or data.get("filename"),
        "extension": data.get("extension"),
        "source": data.get("source"),
    }
    if metadata:
        safe.update(metadata)
    return safe


def record_attachment_observed(
    conversation_id: int | None,
    message_id: int | str | None,
    attachment: dict,
) -> int | None:
    """Create/update the current state for an observed TODY attachment."""
    return record_attachment_result(
        conversation_id,
        message_id,
        attachment,
        status="observed",
        metadata={"observed": True},
    )


def record_attachment_result(
    conversation_id: int | None,
    message_id: int | str | None,
    attachment: dict,
    *,
    status: str,
    error: str | None = None,
    metadata: dict | None = None,
) -> int | None:
    """Update attachment state and emit a matching sanitized event."""
    att_id = _attachment_id(attachment)
    msg_id = str(message_id)[:120] if message_id is not None else None
    error_preview = redact_text(error, max_len=255) if error else None
    retry_status = status in {"failed", "pending_retry", "vision_unavailable", "download_failed"}
    try:
        with session_scope() as s:
            stmt = select(TodyAttachmentState).where(
                TodyAttachmentState.conversation_id == conversation_id,
                TodyAttachmentState.message_id == msg_id,
                TodyAttachmentState.attachment_id == att_id,
            )
            row = s.execute(stmt).scalar_one_or_none()
            if row is None:
                row = TodyAttachmentState(
                    conversation_id=conversation_id,
                    message_id=msg_id,
                    attachment_id=att_id,
                    retry_count=0,
                )
                s.add(row)
            row.mime_type = str((attachment or {}).get("mime_type") or "")[:100] or None
            row.size_bytes = _attachment_size(attachment)
            row.status = (status or "observed")[:32]
            row.last_error = error_preview
            row.metadata_json = _metadata_json(_attachment_metadata(attachment, metadata))
            row.updated_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)
            if retry_status:
                row.retry_count = int(row.retry_count or 0) + 1
                row.next_retry_at = row.updated_at + dt.timedelta(minutes=min(60, row.retry_count * 5))
            s.flush()
            row_id = int(row.id)
        record_event(
            "tody_attachment_state",
            conversation_id=conversation_id,
            message_id=msg_id,
            direction="inbound",
            actor="tody_worker",
            status=status,
            metadata={
                "attachment_id": att_id,
                "mime_type": (attachment or {}).get("mime_type"),
                "error": error_preview,
            },
        )
        return row_id
    except Exception as exc:  # noqa: BLE001
        log_event_safe(
            "tody_attachment_state_failed",
            detail=f"attachment_id={att_id}; status={status}; error={type(exc).__name__}",
            risk_tier="low",
        )
        return None
