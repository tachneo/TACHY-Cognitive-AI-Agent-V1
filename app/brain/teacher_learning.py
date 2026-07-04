"""Teacher-student learning (Phase 1X).

When a real LLM ("teacher") answers, the exchange is stored so the brain can
reuse and adapt that answer later — most importantly when it is running
OFFLINE (no LLM configured, or the model is down / rate-limited). Over time the
brain builds a library of good answers and can hold a real, non-robotic
conversation even with no model available.

Storage: procedural memories under project LEARNED_DIALOGUE (title = the
question asked, content = the LLM's answer). Recall matches on question-token
Jaccard similarity.
"""
from __future__ import annotations

import re

from app.config import get_settings
from app.memory import base_memory
from app.safety.audit_logger import log_event

PROJECT = "LEARNED_DIALOGUE"
_WORD = re.compile(r"[a-z0-9]+")
_STOP = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "did", "do",
    "does", "for", "from", "had", "has", "have", "how", "i", "if", "in", "is",
    "it", "its", "me", "my", "no", "not", "of", "on", "or", "our", "please",
    "so", "that", "the", "their", "them", "then", "there", "these", "they",
    "this", "to", "us", "was", "we", "were", "what", "when", "where", "which",
    "who", "why", "will", "with", "would", "you", "your", "u", "r",
}


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall((text or "").lower()) if w not in _STOP}


def remember_exchange(*, message: str, reply: str, importance: int = 5) -> int | None:
    """Store an LLM answer keyed by its question, for later offline reuse."""
    if not get_settings().teacher_learning_enabled:
        return None
    q = (message or "").strip()
    r = (reply or "").strip()
    if len(q) < 2 or len(r) < 15 or r.startswith("[reply fallback"):
        return None
    # Skip if we already learned a near-identical question (avoid bloat).
    if recall_reply(q, min_score=0.85):
        return None
    mem_id = base_memory.add(
        memory_type="procedural",
        title=q[:200],
        content=r,
        project=PROJECT,
        source_type="teacher",
        importance_score=importance,
        interest_score=6,
    )
    log_event("teacher_learned", detail=f"memory_id={mem_id}; q={q[:60]}")
    return mem_id


def recall_reply(message: str, *, min_score: float = 0.5) -> dict | None:
    """Best matching learned answer for `message`, or None. Jaccard over the
    meaningful question tokens — robust to word order and minor rephrasing."""
    q = _tokens(message)
    if not q:
        return None
    hits = base_memory.search(project=PROJECT, memory_type="procedural", limit=300)
    best, best_score = None, 0.0
    for h in hits:
        t = _tokens(h.title)
        if not t:
            continue
        score = len(q & t) / len(q | t)
        if score > best_score:
            best, best_score = h, score
    if best and best_score >= min_score:
        return {"question": best.title, "reply": best.content,
                "score": round(best_score, 2), "memory_id": best.id}
    return None


def stats() -> dict:
    hits = base_memory.search(project=PROJECT, memory_type="procedural", limit=1000)
    return {"enabled": get_settings().teacher_learning_enabled,
            "learned_replies": len(hits),
            "recent": [{"id": h.id, "question": h.title} for h in hits[:10]]}
