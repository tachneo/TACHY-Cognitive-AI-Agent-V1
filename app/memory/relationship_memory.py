"""Relationship memory subsystem."""
from __future__ import annotations

from app.config import get_settings
from app.memory import base_memory


def guardian_profile() -> dict:
    settings = get_settings()
    return {
        "name": settings.guardian_name,
        "tody_user_uuid": settings.guardian_tody_user_uuid,
        "tody_username": settings.guardian_tody_username,
        "email": settings.guardian_tody_email,
        "role": "guardian_final_authority",
        "direct_reply_allowed": settings.guardian_tody_direct_reply,
    }


def is_guardian_sender(sender: dict | None) -> bool:
    """Verify the immutable TODY identity, with a strict legacy fallback.

    A configured UUID is authoritative. Username and email are accepted only
    together when a deployment has not yet configured the UUID. Display names
    are mutable profile data and never participate in authorization.
    """
    if not sender:
        return False
    profile = guardian_profile()
    expected_uuid = str(profile.get("tody_user_uuid") or "").strip().casefold()
    sender_uuid = str(
        sender.get("uuid")
        or sender.get("user_uuid")
        or sender.get("tody_user_uuid")
        or sender.get("sender_uuid")
        or ""
    ).strip().casefold()
    if expected_uuid:
        return bool(sender_uuid and sender_uuid == expected_uuid)

    if not get_settings().guardian_legacy_identity_fallback_enabled:
        return False

    expected_username = str(profile.get("tody_username") or "").strip().casefold()
    expected_email = str(profile.get("email") or "").strip().casefold()
    username = str(
        sender.get("username") or sender.get("tody_username") or ""
    ).strip().casefold()
    email = str(sender.get("email") or "").strip().casefold()
    return bool(
        expected_username
        and expected_email
        and username == expected_username
        and email == expected_email
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
    """Make sure the guardian relationship is remembered — but ONLY ONCE.

    Previously this ran on every guardian message and created hundreds of
    identical rows (memory pollution). Now it dedups: if a relationship memory
    for the guardian already exists, it returns that id instead of duplicating."""
    profile = guardian_profile()
    existing = base_memory.search(
        memory_type="relationship", query=profile["name"], limit=10)
    # remember_relationship stores title=person[:120], so a title match means
    # the guardian row already exists — don't add another.
    for h in existing:
        if h.title == profile["name"]:
            return int(h.id)
    content = (
        f"{profile['name']} is the guardian/final authority. "
        f"TODY username: {profile['tody_username']}. Email: {profile['email']}. "
        "Conversation with verified guardian should be direct, respectful, and "
        "not blocked by generic social-risk assumptions."
    )
    return remember_relationship(person=profile["name"], content=content)
