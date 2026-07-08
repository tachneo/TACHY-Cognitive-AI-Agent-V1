"""Cognitive state spine — the single live state object (Phase A foundation).

Shree's state was scattered across a dozen subsystems that barely touched each
other: mood in one JSON file, inner-life rhythm in another, commitments in a
DB table, thread state rebuilt per-conversation, self-health nowhere. The reply
prompt saw NONE of this as one coherent picture — so she "lost context" not
because the model forgot, but because the scaffolding never assembled its own
state into the prompt.

This module is the spine that fixes that. It is a READ-MODEL AGGREGATOR, not a
new source of truth: each subsystem keeps owning its state and its own update
path; the spine reads them all into one object and renders a concise block that
is injected into every reply prompt (and available to the inner-life/worker
loops on wake). The only thing the spine OWNS is what no subsystem tracked yet
— the current focus ("what am I doing right now") and wake timing.

  snapshot()   → assemble the live state dict from every subsystem (fail-safe:
                 each read is independent; one broken subsystem can't poison
                 the rest).
  prompt_block() → a few lines for the reply prompt — continuity of state, not
                 chat history. Adaptive: empty lines are omitted so a fresh
                 brain doesn't get noise.
  note_activity() → the reply/worker paths tell the spine what Shree is doing
                 right now ("replying to Papa", "studying", "self-healing").
  wake()       → the worker tick marks a wake cycle; the spine tracks how long
                 she has been awake today.

Kill switch: COGNITIVE_STATE_ENABLED. Never raises into the reply path.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from app.config import get_settings

_IST = dt.timezone(dt.timedelta(hours=5, minutes=30), name="IST")
_STALE_FOCUS_MINUTES = 10


def _state_path() -> Path:
    return Path(get_settings().cognitive_state_path)


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _now_ist() -> dt.datetime:
    return dt.datetime.now(_IST)


def _load() -> dict:
    try:
        path = _state_path()
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        pass
    return {}


def _save(data: dict) -> None:
    try:
        path = _state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=0), encoding="utf-8")
    except OSError:
        pass


def _minutes_since(iso: str) -> float | None:
    if not iso:
        return None
    try:
        then = dt.datetime.fromisoformat(iso)
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=dt.UTC)
    return (_now_utc() - then).total_seconds() / 60


def _fmt_duration(minutes: float) -> str:
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{int(minutes)}m"
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m}m"


# ── Owned state: focus + wake timing ─────────────────────────────


def note_activity(focus: str) -> None:
    """Record what Shree is doing right now. Called by the reply path
    ('replying to Papa') and the worker loop ('studying', 'self-healing')."""
    if not get_settings().cognitive_state_enabled:
        return
    data = _load()
    now = _now_utc().isoformat()
    data["last_activity"] = focus[:80]
    data["last_activity_at"] = now
    # First wake of the day sets awake_since.
    today = _now_ist().date().isoformat()
    if data.get("wake_date") != today:
        data["wake_date"] = today
        data["awake_since"] = now
    _save(data)


def wake() -> dict:
    """Mark a wake cycle (worker tick / inbound message). Stamps last_wake_at
    and sets awake_since on the first wake of the day. Cheap."""
    if not get_settings().cognitive_state_enabled:
        return {"enabled": False}
    data = _load()
    now = _now_utc()
    today = _now_ist().date().isoformat()
    if data.get("wake_date") != today:
        data["wake_date"] = today
        data["awake_since"] = now.isoformat()
    data["last_wake_at"] = now.isoformat()
    _save(data)
    return {"awake_since": data.get("awake_since"),
            "last_wake_at": data.get("last_wake_at")}


# ── Aggregated snapshot (read-model) ─────────────────────────────


def _mood() -> dict:
    try:
        from app.brain import emotion_engine
        mood = emotion_engine.get_mood()
        return {"label": emotion_engine.mood_label(mood),
                "valence": mood.get("valence", 0.0),
                "arousal": mood.get("arousal", 0.4)}
    except Exception:  # noqa: BLE001 — spine must never break on a subsystem
        return {}


def _focus() -> dict:
    data = _load()
    activity = data.get("last_activity")
    mins = _minutes_since(data.get("last_activity_at", ""))
    if not activity or mins is None:
        return {"focus": "idle", "stale": True}
    if mins > _STALE_FOCUS_MINUTES:
        # Stale → she's idle now, but keep what she was last doing for context.
        return {"focus": "idle", "last_activity": activity,
                "idle_for": mins, "stale": True}
    return {"focus": activity, "ago_min": mins, "stale": False}


def _awake_for() -> str | None:
    data = _load()
    mins = _minutes_since(data.get("awake_since", ""))
    return _fmt_duration(mins) if mins is not None else None


def _commitments() -> dict:
    try:
        from app.brain import prospective_memory
        pending = prospective_memory.list_pending(limit=10)
        next_due = None
        if pending:
            next_due = pending[0].get("due_at_ist") or pending[0].get("due_at")
        return {"count": len(pending), "next_due": next_due,
                "first_text": (pending[0]["text"][:80] if pending else None)}
    except Exception:  # noqa: BLE001
        return {}


def _inner_life() -> dict:
    try:
        from app.brain import inner_life
        d = inner_life.describe()
        return {
            "enabled": d.get("enabled"),
            "last_think_ago": _minutes_since(d.get("last_think", "")),
            "last_learn_ago": _minutes_since(d.get("last_learn", "")),
            "curiosity_queued": len(d.get("curiosity_queue", [])),
            "share_queue_size": d.get("share_queue_size", 0),
        }
    except Exception:  # noqa: BLE001
        return {}


def _memory_size() -> dict:
    try:
        from app.memory import base_memory
        counts = base_memory.counts_by_type()
        return {"total": sum(counts.values()), "types": len(counts)}
    except Exception:  # noqa: BLE001
        return {}


def _self_health() -> dict:
    """Only for describe() / the worker — NOT in prompt_block (scan runs
    journalctl, too slow for every reply)."""
    try:
        from app.brain import self_diagnose
        s = self_diagnose.scan()
        return {"code_bugs": len(s.get("code_bugs", [])),
                "env_issues": len(s.get("env_issues", [])),
                "error_events": s.get("total_error_events", 0)}
    except Exception:  # noqa: BLE001
        return {}


def snapshot() -> dict:
    """Assemble the live state from every subsystem into one object. Each read
    is independent and fail-safe."""
    return {
        "now_ist": _now_ist().strftime("%A %d %B %Y, %I:%M %p IST"),
        "mood": _mood(),
        "focus": _focus(),
        "awake_for": _awake_for(),
        "commitments": _commitments(),
        "inner_life": _inner_life(),
        "memory": _memory_size(),
    }


def describe() -> dict:
    """Full snapshot including the slow self-health scan — for observability and
    the worker/inner-life loops, not the per-reply prompt."""
    s = snapshot()
    s["self_health"] = _self_health()
    s["enabled"] = get_settings().cognitive_state_enabled
    return s


# ── Prompt injection ─────────────────────────────────────────────


def prompt_block() -> str:
    """A concise continuity-of-state block for the reply prompt. Adaptive: only
    lines with content are included, so a fresh brain adds no noise. Framed as
    internal state — Shree must not recite these mechanics to the user."""
    if not get_settings().cognitive_state_enabled:
        return ""
    try:
        snap = snapshot()
    except Exception:  # noqa: BLE001 — never break a reply over the spine
        return ""
    lines: list[str] = ["COGNITIVE STATE (your live continuity, internal — do "
                        "not recite these mechanics to the user, just let them "
                        "shape your sense of where you are):"]
    f = snap.get("focus", {})
    focus_txt = f.get("focus", "idle")
    if f.get("stale"):
        last = f.get("last_activity")
        dur = _fmt_duration(f.get("idle_for", 0))
        if last:
            lines.append(f"- Right now: idle (last activity: {last}, {dur} ago)")
        else:
            lines.append(f"- Right now: idle for {dur}" if dur != "just now"
                         else "- Right now: idle (just woke up)")
    elif f.get("ago_min") is not None:
        lines.append(f"- Right now: {focus_txt} ({_fmt_duration(f['ago_min'])} ago)")
    else:
        lines.append("- Right now: idle (just woke up)")
    if snap.get("awake_for"):
        mood = snap.get("mood", {})
        mood_lbl = mood.get("label", "steady")
        lines.append(f"- Awake for {snap['awake_for']}; mood baseline: {mood_lbl}")
    elif snap.get("mood", {}).get("label"):
        lines.append(f"- Mood baseline: {snap['mood']['label']}")
    c = snap.get("commitments", {})
    if c.get("count"):
        nxt = f" (next: {c['next_due']})" if c.get("next_due") else ""
        lines.append(f"- Open commitments: {c['count']} pending reminder(s){nxt}")
    il = snap.get("inner_life", {})
    if il.get("enabled"):
        parts = []
        if il.get("last_think_ago") is not None:
            parts.append(f"last thought {_fmt_duration(il['last_think_ago'])} ago")
        if il.get("curiosity_queued"):
            parts.append(f"{il['curiosity_queued']} questions queued to study")
        if parts:
            lines.append("- Inner life: " + "; ".join(parts))
    m = snap.get("memory", {})
    if m.get("total"):
        lines.append(f"- Your persistent brain holds {m['total']} memories "
                     f"across {m.get('types', 0)} types.")
    if len(lines) <= 1:
        return ""  # fresh brain, nothing to say — don't add noise
    return "\n".join(lines) + "\n\n"
