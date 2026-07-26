"""TODY task-management actions for Shree.

This is the Phase 0 bridge from the brain to chat.tody.in task APIs. It uses
the same authenticated normal-user REST endpoints as the frontend; it never
touches chat-tachy tables directly and never grants admin powers.

Watcher note: current chat-tachy has creator + assignee task visibility, but no
task watcher table/API. Until that exists, "always add Rohit as watcher" is
implemented by forcing Rohit's configured numeric user id into group-task
assignees, which makes him a participant and keeps the task visible to him.
Personal tasks ignore assignees in chat-tachy, so watcher enforcement needs a
group_id.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import get_settings
from app.integrations.tody_client import TodyError, get_client
from app.safety.audit_logger import log_event

_PRIORITIES = {"low", "medium", "high", "urgent"}
_STATUSES = {"open", "in_progress", "done", "blocked", "cancelled"}

_RX_CREATE = re.compile(
    r"^\s*(?:(?:create|add|make|new)\s+(?:a\s+)?(?:tody\s+)?task|(?:tody\s+)?task)\s*"
    r"(?::|-|\bfor\b)?\s*(?P<body>.+)$",
    re.I | re.S,
)
_RX_COMMENT = re.compile(
    r"^\s*(?:comment|reply)\s+(?:on\s+)?(?:tody\s+)?task\s+#?(?P<task_id>\d+)"
    r"\s*(?::|-|\bthat\b)?\s*(?P<body>.+)$",
    re.I | re.S,
)
_RX_STATUS = re.compile(
    r"^\s*(?:mark|set|update)\s+(?:tody\s+)?task\s+#?(?P<task_id>\d+)"
    r"\s+(?:as|to)?\s*(?P<status>open|in_progress|in progress|done|"
    r"blocked|cancelled|canceled)(?:\s*(?::|-|\bnote\b)\s*(?P<notes>.*))?$",
    re.I | re.S,
)
_RX_LIST = re.compile(r"^\s*(?:list|show|check)\s+(?:my\s+)?(?:tody\s+)?tasks\s*$", re.I)
_RX_NATURAL_CREATE = re.compile(
    r"\btask\b.{0,80}\b(?:banao|bana\s*do|banana|create|add|make)\b|"
    r"\b(?:banao|bana\s*do|banana|create|add|make)\b.{0,80}\btask\b",
    re.I | re.S,
)


@dataclass(frozen=True)
class TaskPayload:
    title: str
    description: str | None = None
    deadline: str | None = None
    priority: str = "medium"
    group_id: int | None = None
    assignee_ids: tuple[int, ...] = ()

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "description": self.description,
            "deadline": self.deadline,
            "priority": self.priority,
            "group_id": self.group_id,
            "assignee_ids": list(self.assignee_ids),
        }


def parse_command(message: str) -> dict | None:
    """Parse explicit guardian task commands. Free-form ordinary work requests
    are not auto-converted into TODY tasks; Phase 0 requires task wording."""
    msg = (message or "").strip()
    if not msg or len(msg) > 1200:
        return None

    if _RX_LIST.match(msg):
        return {"action": "list"}

    m = _RX_COMMENT.match(msg)
    if m:
        body = (m.group("body") or "").strip(" :,-\n")
        if body:
            return {
                "action": "comment",
                "task_id": int(m.group("task_id")),
                "body": body[:1000],
            }

    m = _RX_STATUS.match(msg)
    if m:
        status = (m.group("status") or "").strip().lower().replace(" ", "_")
        if status == "canceled":
            status = "cancelled"
        notes = (m.group("notes") or "").strip(" :,-\n") or None
        return {
            "action": "status",
            "task_id": int(m.group("task_id")),
            "status": status,
            "notes": notes[:1000] if notes else None,
        }

    m = _RX_CREATE.match(msg)
    if m:
        payload = _parse_create_body(m.group("body") or "")
        if payload:
            return {"action": "create", **payload.to_dict()}
    if _RX_NATURAL_CREATE.search(msg):
        title = _natural_task_title(msg)
        return {
            "action": "create",
            "title": title,
            "description": _clean_text(msg, 500),
            "deadline": None,
            "priority": "low" if re.search(r"\b(test|testing|qa|check)\b", msg, re.I) else "medium",
            "group_id": None,
            "assignee_ids": [],
        }
    return None


def _parse_create_body(body: str) -> TaskPayload | None:
    fields = _split_fields(body)
    title = fields.pop("title", None)
    if title is None:
        title = fields.pop("_head", "")
    title = _clean_text(title, 180)
    if not title:
        return None

    priority = (fields.pop("priority", "medium") or "medium").strip().lower()
    if priority not in _PRIORITIES:
        priority = "medium"
    description = _clean_text(
        fields.pop("description", fields.pop("desc", "")), 1000,
    ) or None
    deadline = _clean_text(
        fields.pop("deadline", fields.pop("due", "")), 80,
    ) or None
    group_id = _parse_int(fields.pop("group_id", fields.pop("group", "")))
    assignees = _parse_ids(fields.pop("assignees", fields.pop("assignee_ids", "")))
    return TaskPayload(
        title=title,
        description=description,
        deadline=deadline,
        priority=priority,
        group_id=group_id,
        assignee_ids=tuple(assignees),
    )


def _split_fields(text: str) -> dict[str, str]:
    """Accept mobile-friendly command text:

    create task: Fix login | priority: high | due: 2026-08-01 | group: 12
    """
    fields: dict[str, str] = {}
    chunks = [c.strip() for c in re.split(r"\s*\|\s*", text or "") if c.strip()]
    if not chunks:
        return fields
    fields["_head"] = chunks[0]
    for chunk in chunks:
        m = re.match(r"^(title|description|desc|priority|deadline|due|group|group_id|assignees|assignee_ids)\s*:\s*(.+)$", chunk, re.I | re.S)
        if m:
            fields[m.group(1).lower()] = m.group(2).strip()
    return fields


def _clean_text(value: str | None, max_len: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:max_len]


def _natural_task_title(message: str) -> str:
    msg = _clean_text(message, 180)
    low = msg.casefold()
    if "testing" in low or "test" in low:
        return "Test Shree's TODY task creation feature"
    cleaned = re.sub(
        r"\b(?:please|koi|ek|new|naya|tody|task|banao|bana\s*do|banana|"
        r"create|add|make|check\s*karo)\b",
        " ",
        msg,
        flags=re.I,
    )
    cleaned = _clean_text(cleaned, 120)
    return cleaned or "Task from Papa"


def _parse_int(value: str | int | None) -> int | None:
    try:
        out = int(str(value or "").strip())
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def _parse_ids(value: str | list | tuple | None) -> list[int]:
    raw = value if isinstance(value, (list, tuple)) else re.split(r"[, ]+", str(value or ""))
    ids: list[int] = []
    for item in raw:
        parsed = _parse_int(item)
        if parsed and parsed not in ids:
            ids.append(parsed)
    return ids[:50]


def prepare_create_payload(params: dict) -> dict:
    """Normalize a task payload before proposal or execution.

    This function is deterministic and does not call the network so approval
    previews stay fast and hermetic. The execution path may add Rohit's user id
    via the normal-user search API when the numeric env value is absent.
    """
    settings = get_settings()
    title = _clean_text(params.get("title"), 180)
    if not title:
        raise ValueError("task title is required")
    priority = str(params.get("priority") or "medium").strip().lower()
    if priority not in _PRIORITIES:
        priority = "medium"
    group_id = _parse_int(params.get("group_id")) or (
        settings.tody_task_default_group_id if settings.tody_task_default_group_id > 0 else None
    )
    assignee_ids = _parse_ids(params.get("assignee_ids"))
    watcher_mode = "none"
    watcher_warning = None
    if settings.tody_task_force_rohit_watcher:
        rohit_id = int(settings.tody_task_rohit_user_id or 0)
        if group_id and rohit_id > 0:
            if rohit_id not in assignee_ids:
                assignee_ids.append(rohit_id)
            watcher_mode = "assignee_until_chat_tachy_watcher_api_exists"
        elif group_id:
            watcher_warning = "TODY_TASK_ROHIT_USER_ID is not configured; Rohit cannot be auto-added."
        else:
            watcher_warning = "chat-tachy personal tasks ignore assignees; set TODY_TASK_DEFAULT_GROUP_ID to add Rohit."

    return {
        "title": title,
        "description": _clean_text(params.get("description"), 1000) or None,
        "deadline": _clean_text(params.get("deadline"), 80) or None,
        "priority": priority,
        "group_id": group_id,
        "assignee_ids": assignee_ids,
        "watcher_mode": watcher_mode,
        "watcher_warning": watcher_warning,
    }


def _resolve_guardian_user_id() -> int | None:
    settings = get_settings()
    configured = int(settings.tody_task_rohit_user_id or 0)
    if configured > 0:
        return configured
    username = (settings.guardian_tody_username or "").strip().lstrip("@")
    if not username:
        return None
    try:
        data = get_client()._post("/v1/contacts/search_username.php", {"username": username})
    except TodyError:
        return None
    user = data.get("user") if isinstance(data, dict) else None
    return _parse_int(user.get("id") if isinstance(user, dict) else None)


def _enforce_guardian_participant_for_execution(payload: dict) -> dict:
    """Add Rohit as a group-task assignee when possible.

    This is a safety invariant, not an LLM choice. It may strengthen the
    approved payload by adding the guardian participant; it never removes
    assignees or changes title/body/content.
    """
    settings = get_settings()
    out = dict(payload)
    if not settings.tody_task_force_rohit_watcher or not out.get("group_id"):
        return out
    rohit_id = _resolve_guardian_user_id()
    if not rohit_id:
        out["watcher_warning"] = (
            "Rohit user id could not be resolved; task created without auto-watch."
        )
        return out
    assignee_ids = list(out.get("assignee_ids") or [])
    if rohit_id not in assignee_ids:
        assignee_ids.append(rohit_id)
    out["assignee_ids"] = assignee_ids
    out["watcher_mode"] = "assignee_until_chat_tachy_watcher_api_exists"
    out["watcher_warning"] = None
    return out


def do_create_task(params: dict) -> dict:
    if not get_settings().tody_tasks_enabled:
        return {"ok": False, "reason": "TODY task actions are disabled"}
    payload = _enforce_guardian_participant_for_execution(
        prepare_create_payload(params),
    )
    try:
        created = get_client().create_task(
            title=payload["title"],
            description=payload["description"],
            deadline=payload["deadline"],
            priority=payload["priority"],
            group_id=payload["group_id"],
            assignee_ids=payload["assignee_ids"],
        )
    except TodyError as exc:
        return {"ok": False, "reason": f"tody error: {exc}"}
    task = created.get("task") if isinstance(created, dict) else None
    task_id = task.get("id") if isinstance(task, dict) else created.get("id")
    log_event(
        "tody_task_created",
        risk_tier="high",
        detail=(
            f"task_id={task_id}; group_id={payload['group_id']}; "
            f"watcher_mode={payload['watcher_mode']}; title={payload['title'][:80]}"
        ),
    )
    return {"ok": True, "task": task or created, **payload}


def do_list_tasks(group_id: int | None = None) -> dict:
    if not get_settings().tody_tasks_enabled:
        return {"ok": False, "reason": "TODY task actions are disabled"}
    try:
        data = get_client().my_tasks(group_id)
    except TodyError as exc:
        return {"ok": False, "reason": f"tody error: {exc}"}
    return {"ok": True, "tasks": data.get("tasks", data)}


def do_comment_task(task_id: int, body: str) -> dict:
    if not get_settings().tody_tasks_enabled:
        return {"ok": False, "reason": "TODY task actions are disabled"}
    text = _clean_text(body, 1000)
    if not text:
        return {"ok": False, "reason": "empty task comment"}
    try:
        data = get_client().comment_task(int(task_id), text)
    except TodyError as exc:
        return {"ok": False, "reason": f"tody error: {exc}"}
    log_event("tody_task_commented", risk_tier="high", detail=f"task_id={task_id}")
    return {"ok": True, "comment": data.get("comment", data), "body": text}


def do_update_status(task_id: int, status: str, notes: str | None = None) -> dict:
    if not get_settings().tody_tasks_enabled:
        return {"ok": False, "reason": "TODY task actions are disabled"}
    normalized = str(status or "").strip().lower().replace(" ", "_")
    if normalized == "canceled":
        normalized = "cancelled"
    if normalized not in _STATUSES:
        return {"ok": False, "reason": "invalid task status"}
    try:
        data = get_client().update_task_status(int(task_id), normalized, notes)
    except TodyError as exc:
        return {"ok": False, "reason": f"tody error: {exc}"}
    log_event(
        "tody_task_status_updated",
        risk_tier="high",
        detail=f"task_id={task_id}; status={normalized}",
    )
    return {"ok": True, "task": data.get("task", data), "status": normalized}
