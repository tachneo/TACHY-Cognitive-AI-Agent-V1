"""Failure memory — learn from mistakes so Shree stops repeating them.

The reflection loop (self_review) already flags failures (empty reply, prompt
leak, failed verification, denied action); this subsystem gives those failures
a dedicated, recallable store. Before attempting a similar action again, the
brain can recall_recent_failures(kind) and avoid the same path — true learning
from mistakes, not just logging them to the audit table.
"""
from __future__ import annotations

from app.memory import base_memory

_KINDS = {"empty_reply", "prompt_leak", "failed_verification",
          "denied_action", "stuck_loop", "unverified_claim"}


def remember_failure(*, kind: str, context: str, lesson: str = "",
                     importance: int = 7) -> int:
    """Store a failure with its kind, context, and the lesson to avoid repeating
    it. `kind` should be one of _KINDS but any short label is accepted."""
    kind = (kind or "general").strip().lower()[:40]
    content = f"context: {context[:300]}\nlesson: {lesson[:200]}" if lesson \
        else f"context: {context[:400]}"
    return base_memory.add(
        memory_type="failure",
        title=f"Failure: {kind}",
        content=content,
        project="PERSONAL",
        emotion_tag="regret",
        source_type="self_review",
        importance_score=importance,
        is_permanent=False,
        related_module=kind,
    )


def recall_recent_failures(kind: str | None = None, limit: int = 10) -> list[dict]:
    """Recent failures, optionally filtered by kind. Newest first."""
    hits = base_memory.search(memory_type="failure", limit=limit * 3)
    out: list[dict] = []
    for h in hits:
        if kind and h.related_module != kind:
            continue
        out.append({"id": h.id, "title": h.title, "content": h.content,
                    "kind": h.related_module})
        if len(out) >= limit:
            break
    return out


def recall_similar_failures(context: str, limit: int = 5) -> list[dict]:
    """Failures whose context overlaps with the given text — used to avoid
    repeating a mistake in a similar situation."""
    hits = base_memory.recall_rich(context, limit=limit * 2)
    return [{"id": h.id, "title": h.title, "content": h.content,
             "kind": h.related_module}
            for h in hits if h.memory_type == "failure"][:limit]


def failure_count(kind: str | None = None) -> int:
    return len(recall_recent_failures(kind=kind, limit=1000))
