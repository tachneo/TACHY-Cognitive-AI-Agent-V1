"""Manual TODY conversation worker.

This module is intentionally pull-based. It does not start a background thread
or schedule itself. Routes/scripts call it explicitly.
"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field

from app.agents import tody_agent
from app.memory import dialogue_memory
from app.safety.audit_logger import log_event

_LOCK = threading.Lock()


@dataclass
class WorkerState:
    running: bool = False
    last_started_at: float | None = None
    last_finished_at: float | None = None
    last_result: dict | None = None
    last_error: str | None = None
    runs: int = 0
    processed: int = 0
    skipped: int = 0
    locked: bool = False
    mode: str = "idle"
    notes: list[str] = field(default_factory=list)


_STATE = WorkerState()


def status() -> dict:
    data = asdict(_STATE)
    data["locked"] = _LOCK.locked()
    return data


def poll_once(*, dry_run: bool = True, conversation_limit: int = 10,
              message_limit: int = 10) -> dict:
    """Inspect/process at most one latest unprocessed TODY message."""
    if not _LOCK.acquire(blocking=False):
        _STATE.skipped += 1
        return {"processed": False, "locked": True, "reason": "worker already running"}

    _STATE.running = True
    _STATE.mode = "dry_run" if dry_run else "process_once"
    _STATE.last_started_at = time.time()
    _STATE.last_error = None
    _STATE.runs += 1
    try:
        result = _poll_once_unlocked(
            dry_run=dry_run,
            conversation_limit=conversation_limit,
            message_limit=message_limit,
        )
        _STATE.last_result = result
        if result.get("processed"):
            _STATE.processed += 1
        else:
            _STATE.skipped += 1
        log_event(
            "tody_worker_poll_once",
            detail=f"dry_run={dry_run}; processed={result.get('processed')}; reason={result.get('reason', '')}",
            risk_tier="medium",
        )
        return result
    except Exception as exc:
        _STATE.last_error = f"{type(exc).__name__}: {exc}"
        log_event("tody_worker_error", detail=_STATE.last_error, risk_tier="medium")
        raise
    finally:
        _STATE.running = False
        _STATE.mode = "idle"
        _STATE.last_finished_at = time.time()
        _LOCK.release()


def poll_conversation_once(conversation_id: int, *, dry_run: bool = True,
                           message_limit: int = 10) -> dict:
    """Inspect/process one known conversation without scanning the inbox.

    The live TODY worker uses this as the low-latency path for Rohit's active
    guardian chat. It makes one messages API call per tick instead of polling
    the whole conversation list, which keeps the fast path narrow.
    """
    if not _LOCK.acquire(blocking=False):
        _STATE.skipped += 1
        return {"processed": False, "locked": True, "reason": "worker already running"}

    _STATE.running = True
    _STATE.mode = "dry_run_fast" if dry_run else "fast_conversation"
    _STATE.last_started_at = time.time()
    _STATE.last_error = None
    _STATE.runs += 1
    try:
        result = _poll_conversation_unlocked(
            conversation_id,
            dry_run=dry_run,
            message_limit=message_limit,
        )
        _STATE.last_result = result
        if result.get("processed"):
            _STATE.processed += 1
        else:
            _STATE.skipped += 1
        log_event(
            "tody_worker_fast_poll",
            detail=(
                f"conversation_id={conversation_id}; dry_run={dry_run}; "
                f"processed={result.get('processed')}; "
                f"reason={result.get('reason', '')}"
            ),
            risk_tier="medium",
        )
        return result
    except Exception as exc:
        _STATE.last_error = f"{type(exc).__name__}: {exc}"
        log_event("tody_worker_fast_error", detail=_STATE.last_error,
                  risk_tier="medium")
        raise
    finally:
        _STATE.running = False
        _STATE.mode = "idle"
        _STATE.last_finished_at = time.time()
        _LOCK.release()


def _poll_once_unlocked(*, dry_run: bool, conversation_limit: int,
                        message_limit: int) -> dict:
    from app.config import get_settings
    conversations = tody_agent.inbox(limit=conversation_limit)
    convs = _conversation_items(conversations)
    if not convs:
        return {"processed": False, "reason": "no conversations found", "dry_run": dry_run}

    # Autonomous social mode: reply to EVERY conversation with pending messages
    # in one pass (so many people can chat with Shree at once). Otherwise keep
    # the supervised default: process the first pending conversation only.
    process_all = (not dry_run and get_settings().tody_autonomous_social)
    handled: list[dict] = []

    for conv in convs:
        conversation_id = _conversation_id(conv)
        if conversation_id is None:
            continue
        messages = tody_agent.messages(conversation_id, limit=message_limit)
        candidate = _latest_unprocessed_message(conversation_id, messages)
        if candidate is None:
            continue
        if dry_run:
            return {
                "processed": False,
                "dry_run": True,
                "candidate": candidate,
                "reason": "dry run only; no reply drafted or sent",
            }
        kwargs = {"sender": candidate.get("sender"), "message_id": candidate.get("message_id"), "extra_message_ids": candidate.get("extra_message_ids")}
        if candidate.get("attachments"): kwargs["attachments"] = candidate["attachments"]
        result = tody_agent.draft_reply_to_message(conversation_id, candidate["body"], **kwargs)
        result["source_message"] = {
            "id": candidate.get("message_id"),
            "body": candidate.get("body"),
        }
        result["dry_run"] = False
        if not process_all:
            return result
        handled.append({"conversation_id": conversation_id,
                        "sent": result.get("sent"),
                        "throttled": result.get("throttled", False)})

    if handled:
        return {"processed": True, "dry_run": False, "autonomous_social": True,
                "conversations_handled": len(handled), "results": handled}
    return {
        "processed": False,
        "dry_run": dry_run,
        "reason": "no unprocessed text messages found",
    }


def _poll_conversation_unlocked(conversation_id: int, *, dry_run: bool,
                                message_limit: int) -> dict:
    messages = tody_agent.messages(conversation_id, limit=message_limit)
    candidate = _latest_unprocessed_message(conversation_id, messages)
    if candidate is None:
        return {
            "processed": False,
            "dry_run": dry_run,
            "conversation_id": conversation_id,
            "fast_conversation": True,
            "reason": "no unprocessed text messages found",
        }
    if dry_run:
        return {
            "processed": False,
            "dry_run": True,
            "candidate": candidate,
            "conversation_id": conversation_id,
            "fast_conversation": True,
            "reason": "dry run only; no reply drafted or sent",
        }
    kwargs = {"sender": candidate.get("sender"), "message_id": candidate.get("message_id"), "extra_message_ids": candidate.get("extra_message_ids")}
    if candidate.get("attachments"): kwargs["attachments"] = candidate["attachments"]
    result = tody_agent.draft_reply_to_message(conversation_id, candidate["body"], **kwargs)
    result["source_message"] = {
        "id": candidate.get("message_id"),
        "body": candidate.get("body"),
        "batch_size": candidate.get("batch_size", 1),
    }
    result["dry_run"] = False
    result["fast_conversation"] = True
    return result


def _conversation_items(data: dict | list) -> list[dict]:
    if isinstance(data, list):
        return data
    for key in ("conversations", "items", "data"):
        value = data.get(key) if isinstance(data, dict) else None
        if isinstance(value, list):
            return value
    return []


def _conversation_id(row: dict) -> int | None:
    for key in ("id", "conversation_id", "chat_id"):
        value = row.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def _latest_unprocessed_message(conversation_id: int, data: dict | list) -> dict | None:
    """All unprocessed inbound messages batched into ONE turn, oldest→newest —
    so rapid-fire messages get a single, in-order, human-like reply instead of
    out-of-order one-per-tick answers.
    """
    items = tody_agent._message_items(data)  # internal parser shared with agent
    pending: list[dict] = []
    for row in items:  # chronological order
        body = tody_agent._message_body(row)
        attachment = tody_agent._message_attachment(row)
        if not body and not attachment:
            continue
        message_id = row.get("id") or row.get("message_id")
        if message_id is None or dialogue_memory.was_processed(
                "tody", conversation_id, message_id):
            continue
        pending.append({"id": message_id, "body": body,
                        "sender": tody_agent._message_sender(row),
                        "attachment": attachment})
    if not pending:
        return None
    combined = "\n".join(p["body"] for p in pending)
    return {
        "conversation_id": conversation_id,
        "message_id": pending[-1]["id"],           # newest is the reply anchor
        "extra_message_ids": [p["id"] for p in pending[:-1]],
        "body": combined,
        "sender": pending[-1]["sender"],
        "attachments": [p["attachment"] for p in pending if p.get("attachment")],
        "batch_size": len(pending),
    }
