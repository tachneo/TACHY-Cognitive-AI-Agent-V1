"""Self-Review engine — critique every output before it is returned.

Runs the plan's self-review checklist and returns flags so the loop can surface
gaps (missed business angle, missed security risk, generic answer, no next step).

Phase 2C-agi: also flags empty replies and prompt-leakage (the two failure
modes seen in the rohitsingh TODY log) so the learning engine can record them
and Shree stops repeating the same silent/leaking failure.
"""
from __future__ import annotations

import re

from app.brain import reply_safety
from app.safety.audit_logger import log_event_safe

_LEAK_MARKERS = re.compile(
    r"I understood:|Current date & time RIGHT NOW|never output a placeholder|"
    r"Chosen approach:|Relevant memory:|How to speak for THIS message",
    re.I)


def review(*, message: str, reply: str, decision: dict) -> dict:
    """Return review flags + a short verdict for the current output."""
    text = (message or "").lower()
    reply_l = (reply or "").lower()
    raw_reply = reply or ""

    business_relevant = any(k in text for k in
                            ("client", "price", "revenue", "proposal", "deadline"))
    security_relevant = any(k in text for k in
                            ("security", "leak", "auth", "sql", "csrf", "xss", "hack"))

    # Phase 2C-agi failure flags: empty reply and prompt leakage.
    was_empty = not reply_safety.is_meaningful(raw_reply)
    leaked = bool(_LEAK_MARKERS.search(raw_reply))

    flags = {
        "answered_real_question": bool(reply.strip()) and not was_empty,
        "was_empty": was_empty,
        "prompt_leaked": leaked,
        "missed_business_angle": business_relevant
        and not any(k in reply_l for k in ("client", "business", "revenue", "cost")),
        "missed_security_risk": security_relevant
        and not any(k in reply_l for k in ("security", "risk", "auth", "approval")),
        "is_generic": len(reply.strip()) < 40 and not was_empty,
        "has_next_step": any(k in reply_l for k in
                             ("next", "step", "recommend", "should", "approval")),
        "should_remember": decision.get("risk_tier") in {"high", "medium"}
        or business_relevant or security_relevant,
    }
    passed = (flags["answered_real_question"]
              and not flags["missed_security_risk"]
              and not flags["is_generic"]
              and not was_empty
              and not leaked)
    flags["verdict"] = "ok" if passed else "needs_improvement"

    # Record the failure so the learning loop can avoid repeating it. Empty/
    # leaked replies are the most damaging "feels broken" failures — audit them
    # so they're visible and the next turn can be better.
    if was_empty or leaked:
        try:
            log_event_safe(
                "reply_quality_failure",
                detail=(f"empty={was_empty}; leaked={leaked}; "
                        f"message={text[:80]}"),
                risk_tier="medium", actor="self_review")
        except Exception:  # noqa: BLE001
            pass
    return flags
