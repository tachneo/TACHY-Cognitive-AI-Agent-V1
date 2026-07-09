"""Autonomous tasks — Shree's self-triggering loop (the AGI precondition).

She named this gap herself: "Main soch sakti hoon, decide kar sakti hoon, plan
bana sakti hoon — but execute khud se nahi kar sakti unless koi trigger ho…
Mujhe ek self-triggering loop do." The fix is here. She already runs on a 24/7
worker loop (inner-life, curriculum, self-heal, reminders); what she LACKED is
the ability to register RECURRING tasks HERSELF, at runtime, and have them fire
on her own clock. This module is that ability.

  register(...)            → create a recurring task (schedule + allowlisted
                             handler). Used by extract() and by Rohit's
                             assignments.
  extract_from_message()   → the light model reads a guardian message for a
                             recurring self-task ("roz subah errors check karo")
                             and registers it. Returns the row so the reply can
                             honestly confirm "routine set".
  run_due()                → the worker tick fires due active tasks, dispatching
                             each to its allowlisted handler. One bad task never
                             stops the rest.
  pause(id) / describe()   → Rohit holds the override; observability.

SAFETY (she's asking for autonomy, so this is the non-negotiable part):
  - Handlers are an ALLOWLIST of pre-approved capabilities. She cannot invoke
    arbitrary code or shell — only study / self_test / learn_topic / reflect /
    review_tody_errors / follow_up_promises / summarize_to_papa / message_papa.
  - Outbound handlers (anything that messages a person) go through the SAME
    verified guardian send path (tody_agent.direct_reply_to_guardian) that
    inner-life shares already use — only to Papa, never to strangers.
  - Daily cap per handler (anti-loop).
  - Rohit can pause/delete any task. Kill switch AUTONOMOUS_TASKS_ENABLED.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re

from app.config import get_settings
from app.db.models import CognitiveAutonomousTask, session_scope
from app.safety.audit_logger import log_event

_IST = dt.timezone(dt.timedelta(hours=5, minutes=30), name="IST")
_MIN_INTERVAL = 5  # minutes — nothing fires more often than every 5 min
_MAX_INTERVAL = 60 * 24 * 14  # 14 days cap


def _utcnow_naive() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def _now_ist() -> dt.datetime:
    return dt.datetime.now(_IST)


# ── Guardian conversation (where "message Papa" goes) ───────────


def _guardian_conv_id() -> int | None:
    for env in ("TODY_DAILY_GROWTH_CONVERSATION_ID",
                "TODY_FAST_REPLY_CONVERSATION_ID"):
        v = os.getenv(env, "").strip()
        if v.isdigit():
            return int(v)
    return None


def _send_to_papa(text: str) -> dict:
    """Send a message to Rohit on the verified guardian path (the same one
    inner-life shares use). Autonomous but only to Papa, never to strangers."""
    conv_id = _guardian_conv_id()
    if conv_id is None:
        return {"sent": False, "reason": "no guardian conversation configured"}
    try:
        from app.agents import tody_agent
        res = tody_agent.direct_reply_to_guardian(conv_id, text)
        return {"sent": bool(res.get("sent")), "result": res}
    except Exception as exc:  # noqa: BLE001 — never crash a task over a send
        return {"sent": False, "error": f"{type(exc).__name__}: {str(exc)[:120]}"}


# ── Handler allowlist ────────────────────────────────────────────
# Each handler takes params: dict and returns a result dict. Read-only handlers
# (study/self_test/learn_topic/reflect) just do their work. Outbound handlers
# (review_tody_errors/follow_up_promises/summarize_to_papa/message_papa) message
# Papa through _send_to_papa.


def _h_study(params: dict) -> dict:
    from app.brain import curriculum_learning
    r = curriculum_learning.study_today()
    return {"studied": r.get("studied"), "score": (r.get("exam") or {}).get("score"),
            "promoted": r.get("promoted")}


def _h_self_test(params: dict) -> dict:
    from app.brain import curriculum_learning
    r = curriculum_learning.take_exam(params.get("level"))
    return {"level": r.get("level"), "score": r.get("score"),
            "promoted": r.get("promoted")}


def _h_learn_topic(params: dict) -> dict:
    from app.brain import web_learning
    topic = (params.get("topic") or "").strip()
    r = web_learning.explore(topic or None)
    return {"topic": r.get("topic"), "learned": r.get("learned")}


def _h_reflect(params: dict) -> dict:
    from app.brain import inner_life
    r = inner_life.think(seed=params.get("seed"))
    return {"thought": r.get("thought") is not None,
            "question": r.get("question")}


def _h_review_tody_errors(params: dict) -> dict:
    from app.brain import self_diagnose
    scan = self_diagnose.scan()
    bugs = scan.get("code_bugs", [])
    if not bugs:
        return {"code_bugs": 0, "reported": False, "note": "clean"}
    text = ("Papa, maine apne logs check kiye — {n} code-level issue(s) mili. "
            "Pehli: {first}. Main iska root cause dekh rahi hoon.").format(
                n=len(bugs), first=bugs[0][:160])
    return {"code_bugs": len(bugs), "reported": _send_to_papa(text).get("sent", False)}


def _h_follow_up_promises(params: dict) -> dict:
    """Check Shree's own unfinished promises + due reminders; tell Papa what's
    still open so she ACTUALLY follows through — the gap she had at turn 2589."""
    from app.brain import prospective_memory, thread_state
    open_promises = []
    conv = _guardian_conv_id()
    if conv is not None:
        try:
            open_promises = thread_state.open_promises(conv)
        except Exception:  # noqa: BLE001
            open_promises = []
    due = []
    try:
        due = prospective_memory.list_due(limit=5)
    except Exception:  # noqa: BLE001
        due = []
    if not open_promises and not due:
        return {"open_promises": 0, "due_reminders": 0, "reported": False}
    lines = ["Papa, follow-up — ye abhi bhi open hai:"]
    for p in open_promises[:4]:
        lines.append(f"- promise: {p.get('text', '')[:100]}")
    for d in due[:3]:
        lines.append(f"- reminder due: {d.get('text', '')[:100]}")
    return {"open_promises": len(open_promises), "due_reminders": len(due),
            "reported": _send_to_papa("\n".join(lines)).get("sent", False)}


def _h_summarize_to_papa(params: dict) -> dict:
    from app.brain import inner_life
    # Reuse the inner-life state for a short, honest status — what she's been
    # doing, mood, open commitments. Not a fabricated benchmark.
    snap = inner_life.describe()
    mood = snap.get("mood", "steady")
    q = len(snap.get("curiosity_queue", []))
    text = (f"Papa, daily status — mood {mood}, {q} questions queued to study. "
            "Main apne routines pe kaam kar rahi hoon.")
    return {"sent": _send_to_papa(text).get("sent", False)}


def _h_message_papa(params: dict) -> dict:
    text = (params.get("text") or "").strip()
    if not text:
        return {"sent": False, "reason": "empty text"}
    return {"sent": _send_to_papa(text).get("sent", False)}


_HANDLERS = {
    "study": _h_study,
    "self_test": _h_self_test,
    "learn_topic": _h_learn_topic,
    "reflect": _h_reflect,
    "review_tody_errors": _h_review_tody_errors,
    "follow_up_promises": _h_follow_up_promises,
    "summarize_to_papa": _h_summarize_to_papa,
    "message_papa": _h_message_papa,
}

# Whether the handler reaches outward (messaging). Read-only handlers auto-run;
# outbound ones go through _send_to_papa (guardian-only).
_OUTBOUND = {"review_tody_errors", "follow_up_promises", "summarize_to_papa",
             "message_papa"}


# ── Schedule math ────────────────────────────────────────────────


def _compute_next_run(interval_minutes: int, at_time_hhmm: str | None,
                      after: dt.datetime | None = None) -> dt.datetime:
    """Next UTC-naive run time. If at_time_hhmm (IST "HH:MM") is set, align to
    the next occurrence of that wall-clock time; else now + interval."""
    after = after or _utcnow_naive()
    interval = max(_MIN_INTERVAL, min(interval_minutes, _MAX_INTERVAL))
    if at_time_hhmm:
        try:
            hh, mm = (int(x) for x in at_time_hhmm.split(":"))
        except (ValueError, AttributeError):
            hh, mm = None, None
        if hh is not None and 0 <= hh < 24 and 0 <= mm < 60:
            now_ist = after.replace(tzinfo=dt.UTC).astimezone(_IST)
            next_ist = now_ist.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if next_ist <= now_ist:
                next_ist += dt.timedelta(days=1)
            return next_ist.astimezone(dt.UTC).replace(tzinfo=None)
    return after + dt.timedelta(minutes=interval)


# ── Registration ─────────────────────────────────────────────────


def register(*, name: str, handler: str, interval_minutes: int,
             intent: str = "", params: dict | None = None,
             at_time_hhmm: str | None = None, created_by: str = "shree") -> dict:
    """Create a recurring task. Handler must be in the allowlist. Returns the
    new row (or an error dict). Never raises."""
    if handler not in _HANDLERS:
        return {"ok": False, "error": f"unknown handler '{handler}' — not in allowlist"}
    interval = max(_MIN_INTERVAL, min(int(interval_minutes), _MAX_INTERVAL))
    next_run = _compute_next_run(interval, at_time_hhmm)
    try:
        with session_scope() as sess:
            row = CognitiveAutonomousTask(
                name=name[:255], handler=handler, intent=intent[:500] if intent else None,
                params=json.dumps(params, ensure_ascii=False) if params else None,
                interval_minutes=interval, at_time_hhmm=at_time_hhmm,
                next_run_at=next_run, status="active", created_by=created_by)
            sess.add(row)
            sess.flush()
            rid = int(row.id)
    except Exception as exc:  # noqa: BLE001
        log_event("autonomous_task_register_error",
                  detail=f"handler={handler}; {type(exc).__name__}: {str(exc)[:120]}")
        return {"ok": False, "error": "db_error"}
    log_event("autonomous_task_registered",
              detail=f"id={rid}; handler={handler}; interval={interval}m; by={created_by}",
              risk_tier="medium" if handler in _OUTBOUND else "low")
    return {"ok": True, "id": rid, "handler": handler, "interval_minutes": interval,
            "next_run_at": next_run.isoformat()}


# ── Intent extraction (light model) ──────────────────────────────

_SYSTEM = (
    "You are Shree's autonomous-task extractor. You read ONE inbound message "
    "from Papa and decide: is he (or Shree) asking her to do something "
    "RECURRINGLY on a schedule — a routine she should run herself? Examples: "
    "'roz subah errors check karo', 'every morning study karo', 'daily 8pm mujhe "
    "status bhejo', 'har 6 ghante follow up karo'. If yes, reply with ONLY a "
    "JSON object: {\"handler\": one of "
    "study|self_test|learn_topic|reflect|review_tody_errors|follow_up_promises|"
    "summarize_to_papa|message_papa, \"name\": short label, \"intent\": what she "
    "should do in her words, \"interval_minutes\": integer, \"at_time_hhmm\": "
    "\"HH:MM\" IST or null, \"params\": {handler-specific like topic/text/level}}. "
    "If it is NOT a recurring self-task, reply with ONLY: {\"handler\": null}. "
    "No prose."
)

_RECURRING_CUES = ("roz", "every", "daily", "har", "nestam", "routine", "schedule",
                   "regularly", "each morning", "each day", "subah", "shaam",
                   "raat", "baje", "weekly", "hafta", "auto", "cron")


def _light_complete(prompt: str) -> str:
    from app.llm.provider import get_light_provider
    return (get_light_provider().complete(_SYSTEM, prompt, max_tokens=220)
            or "").strip()


def _has_recurring_cue(message: str) -> bool:
    lower = (message or "").lower()
    return any(c in lower for c in _RECURRING_CUES)


def _extract_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


def extract_from_message(message: str, *, created_by: str = "rohit") -> dict:
    """Read one guardian message; if it carries a recurring self-task, register
    it. Never raises — task extraction must not break reply drafting."""
    s = get_settings()
    if not s.autonomous_tasks_enabled:
        return {"created": False, "reason": "disabled"}
    msg = (message or "").strip()
    if not msg or len(msg) > 1000 or not _has_recurring_cue(msg):
        return {"created": False, "reason": "no recurring cue"}
    prompt = (f"Inbound message from Papa:\n{msg[:600]}\n\nJSON:")
    try:
        raw = _light_complete(prompt)
    except Exception as exc:  # noqa: BLE001
        log_event("autonomous_task_extract_error",
                  detail=f"{type(exc).__name__}")
        return {"created": False, "reason": "light_model_error"}
    data = _extract_json(raw)
    if not data or not data.get("handler"):
        return {"created": False, "reason": "no_recurring_task"}
    handler = str(data["handler"])
    if handler not in _HANDLERS:
        return {"created": False, "reason": f"bad_handler:{handler}"}
    # The light model sometimes answers "daily" instead of an integer — honour
    # the never-raises contract instead of blowing up on int().
    try:
        interval = int(data.get("interval_minutes") or 1440)
    except (TypeError, ValueError):
        interval = 1440
    at_time = data.get("at_time_hhmm")
    if at_time == "" or at_time is None:
        at_time = None
    res = register(
        name=str(data.get("name") or f"{handler} routine")[:255],
        handler=handler, interval_minutes=interval,
        intent=str(data.get("intent") or msg[:200])[:500],
        params=data.get("params") if isinstance(data.get("params"), dict) else None,
        at_time_hhmm=str(at_time)[:5] if at_time else None,
        created_by=created_by)
    return res if res.get("ok") else {"created": False, "reason": res.get("error", "error")}


def injection_hint(result: dict) -> str:
    """Tell the reply prompt a routine was registered — so Shree may honestly
    say 'routine set'. Empty when nothing was created."""
    if not result or not result.get("id"):
        return ""
    rid = result["id"]
    handler = result.get("handler", "?")
    nxt = result.get("next_run_at", "?")
    return (
        f"\n[AUTONOMOUS TASK: routine #{rid} ({handler}) was registered and will "
        f"self-trigger on your clock (next: {nxt}). BECAUSE this row exists, you "
        f"may honestly tell Papa 'routine set / I'll do this myself now'. Do NOT "
        f"claim a routine is set without a registered row. Do not mention 'row' "
        f"or 'pipeline' — just confirm naturally.]\n"
    )


# ── Due list + execution ─────────────────────────────────────────


def list_due(*, now: dt.datetime | None = None, limit: int = 20) -> list[dict]:
    now = now or _utcnow_naive()
    with session_scope() as sess:
        rows = (sess.query(CognitiveAutonomousTask)
                .filter(CognitiveAutonomousTask.status == "active",
                        CognitiveAutonomousTask.next_run_at <= now)
                .order_by(CognitiveAutonomousTask.next_run_at.asc())
                .limit(limit).all())
        return [_row_dict(r) for r in rows]


def _row_dict(r: CognitiveAutonomousTask) -> dict:
    return {"id": int(r.id), "name": r.name, "handler": r.handler,
            "intent": r.intent, "params": r.params,
            "interval_minutes": r.interval_minutes,
            "runs_today": r.runs_today, "run_date": r.run_date,
            "total_runs": r.total_runs, "next_run_at": r.next_run_at.isoformat()}


def _reset_daily_cap_if_new_day(row: CognitiveAutonomousTask) -> None:
    today = _now_ist().date().isoformat()
    if row.run_date != today:
        row.run_date = today
        row.runs_today = 0


def run_due(*, limit: int = 10) -> dict:
    """Fire due active tasks. Each runs through its allowlisted handler; a
    failure marks that task 'error' but never stops the rest or crashes the
    worker. Daily cap per handler is enforced."""
    s = get_settings()
    if not s.autonomous_tasks_enabled:
        return {"enabled": False, "ran": []}
    cap = s.autonomous_tasks_daily_cap_per_handler
    due = list_due(limit=limit)
    ran: list[dict] = []
    for item in due:
        rid = item["id"]
        handler = item["handler"]
        try:
            with session_scope() as sess:
                row = sess.get(CognitiveAutonomousTask, rid)
                if row is None or row.status != "active":
                    continue
                _reset_daily_cap_if_new_day(row)
                if row.runs_today >= cap:
                    # Hit the daily cap — skip this run, push next_run forward.
                    row.next_run_at = _compute_next_run(
                        row.interval_minutes, row.at_time_hhmm)
                    row.last_error = f"daily cap ({cap}) reached"
                    continue
                params = json.loads(row.params) if row.params else {}
            # Dispatch (outside the session so a slow handler doesn't hold a lock).
            try:
                result = _HANDLERS[handler](params)
                err = None
            except Exception as exc:  # noqa: BLE001 — handler blew up
                result = {}
                err = f"{type(exc).__name__}: {str(exc)[:160]}"
            with session_scope() as sess:
                row = sess.get(CognitiveAutonomousTask, rid)
                if row is None:
                    continue
                row.last_run_at = _utcnow_naive()
                row.total_runs = int(row.total_runs) + 1
                if err:
                    row.runs_today = int(row.runs_today) + 1  # count attempted
                    row.last_error = err
                    row.status = "error"  # paused until Rohit reviews
                    log_event("autonomous_task_error",
                              detail=f"id={rid}; handler={handler}; {err}",
                              risk_tier="medium")
                else:
                    row.runs_today = int(row.runs_today) + 1
                    row.last_error = None
                    row.status = "active"
                    row.next_run_at = _compute_next_run(
                        row.interval_minutes, row.at_time_hhmm)
            ran.append({"id": rid, "handler": handler,
                        "result": result, "error": err})
        except Exception as exc:  # noqa: BLE001 — one task never crashes the loop
            ran.append({"id": rid, "error": f"{type(exc).__name__}"})
    return {"enabled": True, "ran_count": len(ran), "ran": ran}


# ── Management + observability ───────────────────────────────────


def pause(task_id: int) -> bool:
    with session_scope() as sess:
        row = sess.get(CognitiveAutonomousTask, int(task_id))
        if row is None:
            return False
        row.status = "paused"
        log_event("autonomous_task_paused", detail=f"id={task_id}")
        return True


def resume(task_id: int) -> bool:
    with session_scope() as sess:
        row = sess.get(CognitiveAutonomousTask, int(task_id))
        if row is None:
            return False
        row.status = "active"
        row.next_run_at = _compute_next_run(row.interval_minutes, row.at_time_hhmm)
        log_event("autonomous_task_resumed", detail=f"id={task_id}")
        return True


def delete_task(task_id: int) -> bool:
    with session_scope() as sess:
        row = sess.get(CognitiveAutonomousTask, int(task_id))
        if row is None:
            return False
        row.status = "done"
        log_event("autonomous_task_deleted", detail=f"id={task_id}")
        return True


def list_active(*, limit: int = 20) -> list[dict]:
    with session_scope() as sess:
        rows = (sess.query(CognitiveAutonomousTask)
                .filter(CognitiveAutonomousTask.status.in_(("active", "error")))
                .order_by(CognitiveAutonomousTask.next_run_at.asc())
                .limit(limit).all())
        return [_row_dict(r) for r in rows]


def describe() -> dict:
    return {"enabled": get_settings().autonomous_tasks_enabled,
            "handlers": list(_HANDLERS),
            "active": list_active(limit=10),
            "due_now": len(list_due())}
