"""Social awareness — notice when nobody is answering, and stop.

The failure (20–23 Jul): Rohit stopped replying after a bad exchange. Over the
next 3 days Shree sent 34 consecutive messages into that silence — daily growth
reports, curiosity notes, mission updates ("87 baar baat hui" → "90" → "93"),
and unprompted monologues on Joomla RCE and the TikTok ban. She never noticed
nobody was there.

A person notices after one or two unanswered messages and stops. This module is
that instinct: it counts her outbound messages since the other person last
spoke, and once that crosses the threshold it SUPPRESSES autonomous sends
(reports, curiosity, mission updates, proactive shares). Direct replies to an
actual incoming message are never suppressed — answering is always allowed.

One quiet check-in is permitted at the threshold, then silence until they speak.
Kill switch: SOCIAL_AWARENESS_ENABLED.
"""
from __future__ import annotations

import datetime as dt

from app.config import get_settings
from app.safety.audit_logger import log_event_safe


def unanswered_count(conversation_id: int, *, limit: int = 40) -> int:
    """How many messages she has sent since the other person last spoke."""
    try:
        from app.agents import tody_agent
        data = tody_agent.messages(conversation_id, limit=limit)
        items = tody_agent._message_items(data)
    except Exception:  # noqa: BLE001
        return 0
    count = 0
    for row in reversed(items):  # newest first
        sender = tody_agent._message_sender(row) or {}
        name = str(sender.get("name") or sender.get("username") or "").lower()
        uuid = str(sender.get("uuid") or "")
        is_her = name == "shree" or uuid == _self_uuid()
        if is_her:
            count += 1
        else:
            break
    return count


def _self_uuid() -> str:
    import os
    return (os.getenv("TODY_SELF_UUID") or "").strip()


def may_send_autonomous(conversation_id: int, kind: str = "autonomous") -> dict:
    """Gate for any NON-reply outbound (reports, curiosity, mission updates,
    proactive shares). Returns {"allowed": bool, "reason": str}."""
    s = get_settings()
    if not s.social_awareness_enabled:
        return {"allowed": True, "reason": "awareness disabled"}
    n = unanswered_count(conversation_id)
    threshold = max(1, int(s.social_silence_threshold))
    if n < threshold:
        return {"allowed": True, "reason": f"{n} unanswered", "unanswered": n}
    log_event_safe("autonomous_send_suppressed", risk_tier="low",
                   detail=(f"conv={conversation_id}; kind={kind}; "
                           f"unanswered={n} >= {threshold}"))
    return {"allowed": False, "unanswered": n,
            "reason": (f"{n} messages unanswered — they haven't replied. A "
                       "person would stop here, so I stop.")}


def describe(conversation_id: int) -> dict:
    n = unanswered_count(conversation_id)
    s = get_settings()
    return {"enabled": s.social_awareness_enabled, "unanswered": n,
            "threshold": s.social_silence_threshold,
            "would_suppress": n >= max(1, int(s.social_silence_threshold)),
            "checked_at": dt.datetime.now(dt.UTC).isoformat()}
