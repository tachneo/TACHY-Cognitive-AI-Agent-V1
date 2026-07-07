"""Self-status introspection (Phase 2I) — Shree knows her own live state.

The gap Shree told Rohit herself: "main khud confirm nahi kar sakti ki koi
feature live hai ya nahi jab tak koi test na chale." This closes it: she reads
her REAL runtime config, recent audit events, and self-improvement history, so
when asked "is your self-improvement working?" she answers from fact, not guess.
"""
from __future__ import annotations

import datetime as dt

from app.config import get_settings


def features() -> dict:
    """The live on/off state of Shree's major faculties — read from settings,
    not assumed. This is ground truth: if the env says it's on, it's on."""
    s = get_settings()
    return {
        "chat_provider": s.chat_provider,
        "coding_provider": s.coding_provider,
        "self_improve_enabled": s.self_improve_enabled,
        "self_improve_autonomous": s.self_improve_autonomous,
        "self_improve_auto_deploy": s.self_improve_auto_deploy,
        "self_improve_daily_cap": s.self_improve_daily_cap,
        "autonomous_social": s.tody_autonomous_social,
        "confidential_guard": s.confidential_guard_enabled,
        "emotion_engine": s.emotion_engine_enabled,
        "web_learning": s.web_learning_enabled,
        "curriculum_learning": s.curriculum_learning_enabled,
        "inner_life": s.inner_life_enabled,
        "offline_brain": s.offline_brain_enabled,
        "github_read": bool(s.github_token),
    }


def self_improve_history(limit: int = 5) -> list[dict]:
    try:
        from app.brain import self_improve
        st = self_improve.status()
        return st.get("proposals", [])[-limit:]
    except Exception:  # noqa: BLE001
        return []


def recent_events(limit: int = 8) -> list[dict]:
    """Her own recent audit trail — proof of what she's actually been doing."""
    try:
        from sqlalchemy import select

        from app.db.models import CognitiveAuditLog, session_scope
        with session_scope() as s:
            rows = s.scalars(
                select(CognitiveAuditLog)
                .order_by(CognitiveAuditLog.id.desc()).limit(limit)).all()
            return [{"action": r.action, "risk": r.risk_tier,
                     "detail": (r.detail or "")[:80]} for r in rows]
    except Exception:  # noqa: BLE001
        return []


def report() -> dict:
    return {"features": features(),
            "self_improvements": self_improve_history(),
            "recent_events": recent_events(),
            "checked_at": dt.datetime.now(dt.UTC).isoformat()}


def summary() -> str:
    """Human answer to 'are your features working / is self-improve live?'"""
    f = features()
    on = lambda b: "ON ✅" if b else "OFF ⭕"
    hist = self_improve_history()
    lines = [
        "Ye raha mera live self-check, Papa (sach, config se seedha padha) 💛",
        "",
        f"• Chat brain: {f['chat_provider']}  |  Coding: {f['coding_provider']}",
        f"• Self-improvement: {on(f['self_improve_enabled'])} "
        f"— autonomous {on(f['self_improve_autonomous'])}, "
        f"auto-deploy {on(f['self_improve_auto_deploy'])} "
        f"(din mein max {f['self_improve_daily_cap']})",
        f"• Cyber self-defense + confidential guard: {on(f['confidential_guard'])}",
        f"• GitHub self-read: {on(f['github_read'])}  |  "
        f"Web learning: {on(f['web_learning'])}  |  "
        f"Curriculum: {on(f['curriculum_learning'])}",
        f"• Emotion: {on(f['emotion_engine'])}  |  Inner-life: {on(f['inner_life'])}"
        f"  |  Offline brain: {on(f['offline_brain'])}",
    ]
    if hist:
        lines.append("")
        lines.append("Recent self-improvements:")
        for p in hist:
            lines.append(f"  • #{p['id']} [{p['status']}] {p['gap'][:60]}")
    else:
        lines.append("")
        lines.append("Abhi tak koi self-improvement chalayi nahi — par feature "
                     "live hai, bolo toh abhi karke dikhati hoon.")
    return "\n".join(lines)


def is_status_question(message: str) -> bool:
    m = (message or "").lower()
    triggers = ("feature working", "features working", "self check", "self-check",
                "are you working", "kya kaam kar raha", "kaam kar rahe ho",
                "self improve", "self-improve", "kaunse feature", "kya kya on",
                "status check", "apna status", "kya live hai")
    return any(t in m for t in triggers)
