"""Working memory — per-conversation active-context scratchpad.

Distinct from thread_state (which derives state from dialogue history): this
is an explicit set/get scratchpad for what's active RIGHT NOW in a conversation
— the current task, open sub-questions, what's been established this turn. It
lives in memory keyed by conversation so Shree has a working context, not just
a transcript.
"""
from __future__ import annotations

from app.memory import base_memory

# Working-memory entries are stored as procedural rows keyed by conversation,
# so they're cheap to overwrite and recall. We keep only the latest per
# conversation by archiving older ones on set.


def _key(conversation_id) -> str:
    return f"working:{conversation_id}"


def set_context(*, conversation_id, current_task: str = "",
                open_questions: list[str] | None = None,
                established: list[str] | None = None) -> int:
    """Set/replace the working context for a conversation."""
    parts = []
    if current_task:
        parts.append(f"task: {current_task[:200]}")
    if open_questions:
        parts.append("open: " + " | ".join(open_questions[:6]))
    if established:
        parts.append("established: " + " | ".join(established[:6]))
    content = "\n".join(parts) or "(empty working context)"
    # archive prior working context for this conversation to keep only latest
    for h in base_memory.search(memory_type="procedural",
                                query=_key(conversation_id), limit=20):
        if h.title == _key(conversation_id):
            base_memory.archive(h.id)
    return base_memory.add(
        memory_type="procedural",
        title=_key(conversation_id),
        content=content[:1000],
        project="TODY",
        emotion_tag="neutral",
        source_type="working_memory",
        importance_score=5,
        is_permanent=False,
        related_module=str(conversation_id),
    )


def get_context(conversation_id) -> dict | None:
    """Read the current working context for a conversation, or None."""
    for h in base_memory.search(memory_type="procedural",
                                query=_key(conversation_id), limit=10):
        if h.title == _key(conversation_id):
            return {"id": h.id, "content": h.content,
                    "conversation_id": str(conversation_id)}
    return None


def clear(conversation_id) -> None:
    for h in base_memory.search(memory_type="procedural",
                                query=_key(conversation_id), limit=10):
        if h.title == _key(conversation_id):
            base_memory.archive(h.id)
