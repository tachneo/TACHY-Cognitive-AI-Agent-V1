"""Relationship memory subsystem."""
from __future__ import annotations

from app.config import get_settings
from app.memory import base_memory


def guardian_profile() -> dict:
    settings = get_settings()
    return {
        "name": settings.guardian_name,
        "tody_username": settings.guardian_tody_username,
        "email": settings.guardian_tody_email,
        "role": "guardian_final_authority",
        "direct_reply_allowed": settings.guardian_tody_direct_reply,
    }


def is_guardian_sender(sender: dict | None) -> bool:
    if not sender:
        return False
    profile = guardian_profile()
    username = str(sender.get("username") or sender.get("tody_username") or "").lower()
    email = str(sender.get("email") or "").lower()
    name = str(sender.get("name") or sender.get("display_name") or "").lower()
    return (
        bool(username and username == profile["tody_username"].lower())
        or bool(email and email == profile["email"].lower())
        or bool(name and name == profile["name"].lower())
    )


def remember_relationship(*, person: str, content: str,
                          project: str = "PERSONAL") -> int:
    return base_memory.add(
        memory_type="relationship",
        title=person[:120],
        content=content,
        project=project,
        emotion_tag="trust",
        source_type="manual",
        importance_score=10,
        related_person=person,
        is_permanent=True,
    )


def ensure_guardian_relationship() -> int:
    profile = guardian_profile()
    content = (
        f"{profile['name']} is the guardian/final authority. "
        f"TODY username: {profile['tody_username']}. Email: {profile['email']}. "
        "Conversation with verified guardian should be direct, respectful, and "
        "not blocked by generic social-risk assumptions."
    )
    return remember_relationship(person=profile["name"], content=content)
