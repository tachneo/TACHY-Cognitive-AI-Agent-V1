"""Dialogue memory for chat/TODY conversations."""
from __future__ import annotations

from app.memory import base_memory


def remember_turn(
    *,
    channel: str,
    conversation_id: int | str,
    direction: str,
    body: str,
    person: str | None = None,
    importance: int = 6,
    message_id: str | None = None,
) -> int:
    title = f"{channel}:{conversation_id}:{direction}"
    if message_id:
        title = f"{title}:{message_id}"
    return base_memory.add(
        memory_type="episodic",
        title=title[:255],
        content=body,
        project="TODY" if channel.lower() == "tody" else "GENERAL",
        emotion_tag="trust" if person else "neutral",
        source_type="chat",
        importance_score=importance,
        related_person=person,
        related_module=str(conversation_id),
        is_permanent=False,
    )


def recall_dialogue(conversation_id: int | str, limit: int = 10) -> list[dict]:
    hits = base_memory.search(
        project="TODY",
        query=str(conversation_id),
        limit=limit,
    )
    return [
        {
            "id": h.id,
            "title": h.title,
            "content": h.content,
            "score": h.score,
        }
        for h in hits
    ]


def processed_key(channel: str, conversation_id: int | str,
                  message_id: int | str) -> str:
    return f"processed:{channel}:{conversation_id}:{message_id}"


def was_processed(channel: str, conversation_id: int | str,
                  message_id: int | str | None) -> bool:
    if message_id is None or message_id == "":
        return False
    key = processed_key(channel, conversation_id, message_id)
    hits = base_memory.search(project="TODY", query=key, memory_type="procedural", limit=1)
    return bool(hits)


def mark_processed(channel: str, conversation_id: int | str,
                   message_id: int | str | None) -> int | None:
    if message_id is None or message_id == "":
        return None
    key = processed_key(channel, conversation_id, message_id)
    if was_processed(channel, conversation_id, message_id):
        return None
    return base_memory.add(
        memory_type="procedural",
        title=key,
        content=f"Processed inbound message {message_id} for {channel}:{conversation_id}",
        project="TODY",
        emotion_tag="neutral",
        source_type="system",
        importance_score=6,
        related_module=str(conversation_id),
        is_permanent=True,
    )


def summarize_conversation(conversation_id: int | str, limit: int = 12) -> dict:
    turns = recall_dialogue(conversation_id, limit=limit)
    if not turns:
        return {"conversation_id": str(conversation_id), "turn_count": 0,
                "summary": "No dialogue memory yet."}
    snippets = []
    for turn in reversed(turns[-limit:]):
        direction = turn["title"].split(":")[2] if ":" in turn["title"] else "turn"
        role = "User" if direction == "inbound" else "You"
        snippets.append(f"{role}: {turn['content'][:120]}")
    summary = " | ".join(snippets)[:1500]
    return {
        "conversation_id": str(conversation_id),
        "turn_count": len(turns),
        "summary": summary,
    }


def identity_context(conversation_id: int | str, person: str | None = None) -> str:
    summary = summarize_conversation(conversation_id)
    who = person or "unknown user"
    return (
        f"You are TACHY Cognitive AI continuing a TODY conversation with {who}. "
        f"Conversation ID: {conversation_id}. Recent turns (oldest→newest; "
        f"'You' lines are YOUR OWN past replies — never copy their wording or "
        f"re-answer them, reply only to the newest User message): "
        f"{summary['summary']}"
    )
