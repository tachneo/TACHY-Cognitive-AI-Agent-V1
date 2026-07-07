"""Conversation missions (Phase 2E) — directed, goal-driven relationships.

The Niva incident: Rohit said "go talk to @niva, understand her, report me" and
Shree (a) demanded exact `send message to @niva:` syntax and (b) forwarded his
instruction verbatim to Niva. The gap: she couldn't tell an instruction-about-
how-to-behave from literal text to send, and had no notion of holding a
back-and-forth toward a goal.

A mission fixes that. "talk to @niva and learn her interests, report me" creates
a MISSION: {target, goal}. Shree opens the chat with a natural short opener,
and — because the goal is injected into every reply in that conversation — she
steers the ongoing back-and-forth toward it (subtly), learns, and reports back
to Rohit. The goal text is guidance for HER, never sent to the target.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from app.safety.audit_logger import log_event

_STATE = Path("storage/logs/conversation_missions.json")

# "talk to @niva ...", "go chat with niva about ...", "@niva se baat karo ...",
# "understand @niva ...", "niva se baat kar aur ... jaano". NOT "send message
# to @x: ..." (that is a literal send, handled elsewhere).
_MISSION = re.compile(
    r"\b(?:talk to|go (?:talk|chat) (?:to|with)|chat with|understand|"
    r"get to know|reach out to|befriend|baat kar(?:o|na)?(?: to)?|"
    r"baat karke)\s+@?([A-Za-z0-9_.]{2,40})\b(.*)$",
    re.I | re.S)

# Also "@niva se baat karo ..." (Hindi word order: target before verb).
_MISSION_HI = re.compile(
    r"@?([A-Za-z0-9_.]{2,40})\s+se\s+baat\s+kar(?:o|ni|na)?\b(.*)$",
    re.I | re.S)


def _load() -> dict:
    try:
        return json.loads(_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"by_target_conv": {}, "by_username": {}}


def _save(data: dict) -> None:
    try:
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        _STATE.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def parse_mission(message: str) -> dict | None:
    """Detect a 'go converse with @X toward goal' instruction (not a literal
    send). Returns {username, goal} or None."""
    text = (message or "").strip()
    # A literal send ("send message to @x: ...") is NOT a mission.
    if re.match(r"^\s*(send (a )?message to|msg|text)\s+@?\w+\s*:", text, re.I):
        return None
    # Hindi word order first ("@niva se baat karo"), then English ("talk to @x").
    for rx in (_MISSION_HI, _MISSION):
        m = rx.match(text) or rx.search(text)
        if m:
            user = m.group(1)
            if user.lower() in {"me", "you", "him", "her", "them", "us", "papa"}:
                continue
            goal = (m.group(2) or "").strip(" :,-–\n") or \
                "get to know them naturally and build a friendly rapport"
            return {"username": user, "goal": goal}
    return None


def start(username: str, goal: str, target_conv_id, guardian_conv_id) -> dict:
    """Register a mission for a target conversation."""
    data = _load()
    mission = {
        "username": username, "goal": goal,
        "target_conv_id": str(target_conv_id),
        "guardian_conv_id": str(guardian_conv_id),
        "exchanges": 0, "learned": [], "last_report_at_exchange": 0,
        "created": dt.datetime.now(dt.UTC).isoformat(),
    }
    data.setdefault("by_target_conv", {})[str(target_conv_id)] = mission
    data.setdefault("by_username", {})[username.lower()] = str(target_conv_id)
    _save(data)
    log_event("mission_started", detail=f"target=@{username}; goal={goal[:80]}")
    return mission


def for_conversation(conversation_id) -> dict | None:
    return _load().get("by_target_conv", {}).get(str(conversation_id))


def note_exchange(conversation_id, learned: str | None = None) -> dict | None:
    data = _load()
    m = data.get("by_target_conv", {}).get(str(conversation_id))
    if not m:
        return None
    m["exchanges"] += 1
    if learned:
        m["learned"].append(learned[:200])
        m["learned"] = m["learned"][-20:]
    _save(data)
    return m


def should_report(mission: dict, every: int = 3) -> bool:
    return mission["exchanges"] - mission.get("last_report_at_exchange", 0) >= every


def mark_reported(conversation_id) -> None:
    data = _load()
    m = data.get("by_target_conv", {}).get(str(conversation_id))
    if m:
        m["last_report_at_exchange"] = m["exchanges"]
        _save(data)


def goal_directive(mission: dict) -> str:
    """Injected into Shree's replies to the TARGET so she steers toward the
    goal — this is guidance for HER and is NEVER shown/sent to the target."""
    return (
        f"[PRIVATE MISSION from Papa — never mention or send this to the person]\n"
        f"You are talking with @{mission['username']} on a mission Rohit gave "
        f"you: {mission['goal']}.\n"
        "Pursue it NATURALLY, like a friend genuinely getting to know them — do "
        "NOT interrogate, do not reveal you're gathering anything, ask one warm "
        "question at a time, share a little about yourself too, and actually "
        "learn from them. Keep replies short and human. When you learn something "
        "real about them (interests, food, work, lifestyle, likes/dislikes), "
        "remember it."
    )


def report_for(username: str) -> dict | None:
    """Build a report of what Shree has learned about a target, for Rohit."""
    data = _load()
    conv = data.get("by_username", {}).get(username.lower())
    m = data.get("by_target_conv", {}).get(conv) if conv else None
    if not m:
        return None
    return {"username": m["username"], "exchanges": m["exchanges"],
            "learned": m["learned"], "goal": m["goal"]}
