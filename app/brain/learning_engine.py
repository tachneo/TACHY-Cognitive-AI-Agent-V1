"""Learning engine — close the loop by persisting what matters.

After a pass, if the self-review marks the exchange worth keeping, store an
episodic memory tagged with project, emotion, and priority so it grounds future
recall. Higher-level lesson/behavior/interest updates land in Phase 1C.
"""
from __future__ import annotations

from collections import Counter

from app.brain.attention_system import Signals, priority_score
from app.db.models import CognitiveReflection, session_scope
from app.memory import base_memory


def _emotion_from_signals(s: Signals) -> str:
    if s.security_risk >= 7:
        return "risk"
    if s.urgency >= 7:
        return "urgent"
    if s.emotional_weight >= 7:
        return "pressure"
    return "neutral"


def learn(*, message: str, decision: dict, review: dict, signals: Signals) -> dict:
    """Persist an episodic memory when the review says it's worth remembering."""
    if not review.get("should_remember"):
        return {"saved": False}

    score = priority_score(signals)
    mem_id = base_memory.add(
        memory_type="episodic",
        title=message.strip()[:120] or "interaction",
        content=message.strip(),
        project=decision.get("project", "GENERAL"),
        emotion_tag=_emotion_from_signals(signals),
        source_type="chat",
        importance_score=min(10, max(1, score // 7)),
        urgency_score=signals.urgency,
        emotional_weight=signals.emotional_weight,
        risk_score=signals.security_risk,
        future_action=decision.get("chosen"),
        is_permanent=score >= 60,
    )
    return {"saved": True, "memory_id": mem_id, "priority": score}


def daily_reflection(limit: int = 100) -> dict:
    """Summarise recent memories into lessons and persist a reflection row.

    The Phase-1C version is statistical (counts by type/project/emotion + pulls
    stored lessons); an LLM can author richer narrative in a later phase.
    """
    recent = base_memory.search(limit=limit)
    if not recent:
        return {"saved": False, "note": "no memories yet"}

    by_project = Counter(h.project for h in recent)
    by_emotion = Counter(h.emotion_tag for h in recent)
    summary = (
        f"Reviewed {len(recent)} recent memories. "
        f"Top projects: {dict(by_project.most_common(3))}. "
        f"Emotional tone: {dict(by_emotion.most_common(3))}."
    )
    lessons = "; ".join(
        f"[{h.project}] {h.title}" for h in recent
        if h.memory_type in {"failure", "decision"}
    )[:2000] or "No failure/decision memories to learn from yet."

    with session_scope() as s:
        row = CognitiveReflection(summary=summary, lessons=lessons)
        s.add(row)
        s.flush()
        rid = int(row.id)
    return {"saved": True, "reflection_id": rid, "summary": summary, "lessons": lessons}
