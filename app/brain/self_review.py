"""Self-Review engine — critique every output before it is returned.

Runs the plan's self-review checklist and returns flags so the loop can surface
gaps (missed business angle, missed security risk, generic answer, no next step).
"""
from __future__ import annotations


def review(*, message: str, reply: str, decision: dict) -> dict:
    """Return review flags + a short verdict for the current output."""
    text = (message or "").lower()
    reply_l = (reply or "").lower()

    business_relevant = any(k in text for k in
                            ("client", "price", "revenue", "proposal", "deadline"))
    security_relevant = any(k in text for k in
                            ("security", "leak", "auth", "sql", "csrf", "xss", "hack"))

    flags = {
        "answered_real_question": bool(reply.strip()),
        "missed_business_angle": business_relevant
        and not any(k in reply_l for k in ("client", "business", "revenue", "cost")),
        "missed_security_risk": security_relevant
        and not any(k in reply_l for k in ("security", "risk", "auth", "approval")),
        "is_generic": len(reply.strip()) < 40,
        "has_next_step": any(k in reply_l for k in
                             ("next", "step", "recommend", "should", "approval")),
        "should_remember": decision.get("risk_tier") in {"high", "medium"}
        or business_relevant or security_relevant,
    }
    passed = (flags["answered_real_question"]
              and not flags["missed_security_risk"]
              and not flags["is_generic"])
    flags["verdict"] = "ok" if passed else "needs_improvement"
    return flags
