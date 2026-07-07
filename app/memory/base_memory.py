"""Base memory store — CRUD + recall over the single cognitive_memories table.

All 15 memory *types* share this store; the type-specific modules
(episodic_memory, failure_memory, ...) are thin wrappers that set memory_type.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import func, or_, select

from app.db.models import CognitiveMemory, session_scope

_WORD = re.compile(r"[a-z0-9]+")

# Function words carry no meaning for recall; without this, chat-log memories
# full of conversational filler outrank actual knowledge on every question.
_STOPWORDS = {
    "a", "about", "an", "and", "are", "as", "at", "be", "but", "by", "can",
    "did", "do", "does", "for", "from", "had", "has", "have", "how", "i",
    "if", "in", "is", "it", "its", "me", "my", "no", "not", "of", "on",
    "or", "our", "please", "recently", "so", "tell", "that", "the", "their",
    "them", "then", "there", "these", "they", "this", "to", "us", "was",
    "we", "were", "what", "when", "where", "which", "who", "why", "will",
    "with", "would", "you", "your",
}


@dataclass
class MemoryHit:
    id: int
    memory_type: str
    project: str
    title: str
    content: str
    emotion_tag: str
    score: float  # recall relevance, not stored


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall((text or "").lower()))


def add(
    *,
    memory_type: str,
    title: str,
    content: str,
    project: str = "GENERAL",
    emotion_tag: str = "neutral",
    source_type: str = "chat",
    importance_score: int = 5,
    urgency_score: int = 5,
    emotional_weight: int = 5,
    risk_score: int = 5,
    business_value_score: int = 5,
    interest_score: int = 5,
    lesson_learned: str | None = None,
    future_action: str | None = None,
    avoid_action: str | None = None,
    is_permanent: bool = False,
    related_person: str | None = None,
    related_client: str | None = None,
    related_module: str | None = None,
) -> int:
    """Persist a memory and return its id."""
    with session_scope() as s:
        m = CognitiveMemory(
            memory_type=memory_type, title=title[:255], content=content,
            project=project, emotion_tag=emotion_tag, source_type=source_type,
            importance_score=importance_score, urgency_score=urgency_score,
            emotional_weight=emotional_weight, risk_score=risk_score,
            business_value_score=business_value_score, interest_score=interest_score,
            lesson_learned=lesson_learned, future_action=future_action,
            avoid_action=avoid_action, is_permanent=is_permanent,
            related_person=related_person, related_client=related_client,
            related_module=related_module,
        )
        s.add(m)
        s.flush()
        return int(m.id)


def search(
    *, query: str | None = None, memory_type: str | None = None,
    project: str | None = None, limit: int = 20,
) -> list[MemoryHit]:
    """Filtered listing (LIKE match), newest first. Use recall() for ranked recall."""
    with session_scope() as s:
        stmt = select(CognitiveMemory).where(CognitiveMemory.is_archived.is_(False))
        if memory_type:
            stmt = stmt.where(CognitiveMemory.memory_type == memory_type)
        if project:
            stmt = stmt.where(CognitiveMemory.project == project)
        if query:
            like = f"%{query}%"
            stmt = stmt.where(or_(CognitiveMemory.title.like(like),
                                  CognitiveMemory.content.like(like)))
        stmt = stmt.order_by(CognitiveMemory.created_at.desc()).limit(limit)
        return [_hit(m, 0.0) for m in s.scalars(stmt).all()]


def recall(text: str, *, project: str | None = None, limit: int = 5) -> list[MemoryHit]:
    """Lightweight keyword-overlap recall (Phase 1B).

    Vector/semantic recall is a Phase-1C upgrade; this gives useful grounding now.
    Permanent and high-importance memories get a relevance boost.
    """
    q = _tokens(text) - _STOPWORDS or _tokens(text)
    if not q:
        return []
    with session_scope() as s:
        stmt = select(CognitiveMemory).where(CognitiveMemory.is_archived.is_(False))
        if project:
            stmt = stmt.where(CognitiveMemory.project == project)
        rows = s.scalars(stmt.limit(500)).all()
        scored: list[MemoryHit] = []
        for m in rows:
            overlap = len(q & _tokens(f"{m.title} {m.content}"))
            if not overlap:
                continue
            score = overlap + (m.importance_score / 10.0)
            if m.is_permanent:
                score += 2.0
            if m.memory_type == "semantic":
                # Learned knowledge/facts beat chat-log noise on informational
                # queries (Phase 1O: web-learned lessons must ground replies).
                score += 1.5
            if m.related_module and (_tokens(m.related_module) & q):
                # The question names this memory's topic — strongest signal.
                score += 3.0
            scored.append(_hit(m, round(score, 2)))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:limit]


def _hit(m: CognitiveMemory, score: float) -> MemoryHit:
    return MemoryHit(
        id=int(m.id), memory_type=m.memory_type, project=m.project,
        title=m.title, content=m.content, emotion_tag=m.emotion_tag, score=score,
    )


def counts_by_type() -> dict[str, int]:
    """How many memories of each type — used by the self-model to truthfully
    report the size of Shree's persistent brain."""
    with session_scope() as s:
        rows = s.execute(
            select(CognitiveMemory.memory_type,
                   func.count(CognitiveMemory.id))
            .where(CognitiveMemory.is_archived.is_(False))
            .group_by(CognitiveMemory.memory_type)
        ).all()
    return {str(t): int(n) for t, n in rows}


def recall_rich(text: str, *, limit: int = 5) -> list[MemoryHit]:
    """Same as recall() but here so callers can get ranked hits with content
    for grounding replies in WHAT she remembers, not just titles."""
    return recall(text, limit=limit)


def search_by_person(person: str, *, limit: int = 20) -> list[MemoryHit]:
    """All non-archived memories whose related_person matches `person`
    (case-insensitive).

    Used for action continuity: 'did Niva reply?' needs Shree's interactions
    WITH Niva, which are stored under related_person, not in the title/content
    that the generic search() filters on."""
    name = (person or "").strip()
    if not name:
        return []
    with session_scope() as s:
        stmt = (select(CognitiveMemory)
                .where(CognitiveMemory.is_archived.is_(False))
                .where(func.lower(CognitiveMemory.related_person) == name.lower()))
        rows = s.scalars(stmt.limit(limit)).all()
        return [_hit(m, 0.0) for m in rows]
