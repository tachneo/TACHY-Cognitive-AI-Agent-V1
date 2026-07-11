"""TODY individual-chat actions — like/react, reply, star, forward, post.

Rohit asked Shree to like / reply / comment on TODY chats and she couldn't —
the TodyClient already exposes add_reaction / reply / star / forward /
create_post, but the brain had no way to INVOKE them: she could only
send_message via the 'send message to @username' command. This module is the
missing action layer.

Flow (mirrors the existing directed-messaging command):
  parse_command(message)  → detect a social action + target from Papa's words
  resolve_target(...)     → @username → conversation → their latest message id
  execute / propose       → outward actions go through the SAME approval gate;
                            private ones (star) run immediately

Safety: only the guardian can drive these (the caller passes is_guardian).
Outbound social actions (react/reply/post/forward) are visible to other people,
so in supervised mode they queue an approval Papa confirms; in autonomous-social
mode his instruction IS the authorization. Star is private (only Papa sees it),
so it runs now. Nothing here can touch a non-guardian's schedule or secrets.
"""
from __future__ import annotations

import re

from app.integrations.tody_client import TodyError, get_client
from app.safety.audit_logger import log_event

# ── Command grammar ──────────────────────────────────────────────
# Kept deterministic (not LLM) so an action on someone else's chat is never a
# hallucination. Each returns (action, groups) or None.

_EMOJI = r"(?P<emoji>[☀-➿\U0001f300-\U0001faff❤♥]+)"
_U1 = r"@?(?P<user>[A-Za-z0-9_.]{2,40})"
_U2 = r"@?(?P<user2>[A-Za-z0-9_.]{2,40})"

# "like @niva ka message", "react ❤️ to @niva", "@niva ke message pe heart laga"
_RX_REACT = re.compile(
    rf"\b(?:like|react(?:\s+with)?|reaction|heart|thumbs?\s*up|dil|"
    rf"pasand)\b.*?(?:{_EMOJI}\s*)?(?:to|on|pe|par|ka|ke|@)\s*{_U1}"
    rf"|{_U2}\s*(?:ke|ka|ki)?\s*(?:message|chat|msg)?\s*(?:pe|par|ko)?\s*"
    rf"(?:like|react|heart|dil|pasand)(?:\s+kar[oi]?)?", re.I)
# "reply @niva: text", "reply to @niva that ...", "@niva ko reply karo: text"
_RX_REPLY = re.compile(
    rf"\breply\b.*?{_U1}\s*(?:[:,-]|that|ki|ko|se)?\s*(?P<body>.+)"
    rf"|{_U2}\s*ko\s+reply\s*(?:kar[oi]?)?\s*[:,-]?\s*(?P<body2>.+)", re.I)
# "star @niva ka message", "@niva ke message ko star karo"
_RX_STAR = re.compile(rf"\bstar\b.*?{_U1}|{_U2}\s*(?:ka|ke).*?\bstar\b", re.I)
# "post: text", "comment: text", "status laga: text", "post karo ki text"
_RX_POST = re.compile(
    r"\b(?:post|comment|status)\b\s*(?:karo|kar\s+do|laga(?:o|do)?|update)?\s*"
    r"(?:[:,-]|ki|that)?\s*(?P<body>.+)", re.I)

_DEFAULT_EMOJI = "❤️"
_EMOJI_WORD = {"heart": "❤️", "dil": "❤️", "thumbs up": "👍", "thumbsup": "👍",
               "like": "👍", "pasand": "👍", "fire": "🔥", "laugh": "😂",
               "sad": "😢", "wow": "😮", "clap": "👏"}


def parse_command(message: str) -> dict | None:
    """Detect a TODY social action in Papa's message. Order matters: reply and
    post carry a body, so check them before the bare react/star matchers."""
    msg = (message or "").strip()
    if not msg or len(msg) > 600:
        return None

    m = _RX_REPLY.search(msg)
    if m and (m.group("body") or m.group("body2")):
        body = (m.group("body") or m.group("body2") or "").strip(" :,-\n")
        user = _first_user(m)
        if body and user:
            return {"action": "reply", "user": user, "body": body[:1000]}

    # post/comment must NOT be a reply (already handled) and needs a body
    if re.search(r"\b(?:post|comment|status)\b", msg, re.I):
        m = _RX_POST.search(msg)
        if m and (m.group("body") or "").strip(" :,-\n"):
            return {"action": "post", "body": m.group("body").strip(" :,-\n")[:2000]}

    m = _RX_STAR.search(msg)
    if m:
        user = _first_user(m)
        if user:
            return {"action": "star", "user": user}

    m = _RX_REACT.search(msg)
    if m:
        user = _first_user(m)
        if user:
            emoji = _pick_emoji(m, msg)
            return {"action": "react", "user": user, "emoji": emoji}
    return None


def _first_user(m: re.Match) -> str | None:
    for key in ("user", "user2"):
        if key in m.groupdict() and m.group(key):
            return m.group(key)
    return None


def _pick_emoji(m: re.Match, msg: str) -> str:
    if m.groupdict().get("emoji"):
        return m.group("emoji")
    low = msg.lower()
    for word, emoji in _EMOJI_WORD.items():
        if word in low:
            return emoji
    return _DEFAULT_EMOJI


# ── Target resolution ────────────────────────────────────────────


def resolve_target(username: str) -> dict | None:
    """@username → {conversation_id, message_id (their latest inbound),
    display_name}. None if the user/conversation/message can't be found."""
    from app.agents import tody_messaging
    user = tody_messaging.resolve_username(username)
    if user is None:
        return None
    try:
        conv = get_client().start_direct(user["uuid"])
        conv_id = conv.get("conversation_id")
        if not conv_id:
            return None
        msgs = get_client().messages(int(conv_id), limit=20)
    except TodyError:
        return None
    items = msgs.get("messages") or msgs.get("data") or []
    # Their latest message (a reaction/reply/star targets THEIR message, not ours)
    target_id = None
    for row in reversed(items):  # newest last → walk back
        sender = str(row.get("sender_username") or row.get("username") or "")
        if sender and sender.lstrip("@").lower() != user["username"].lower():
            continue  # skip our own messages
        target_id = row.get("id") or row.get("message_id")
        if target_id:
            break
    if target_id is None and items:  # fall back to the newest message of any side
        last = items[-1]
        target_id = last.get("id") or last.get("message_id")
    if target_id is None:
        return None
    return {"conversation_id": int(conv_id), "message_id": int(target_id),
            "username": user["username"], "display_name": user["display_name"]}


# ── Execution (called by action_engine executors) ────────────────


def do_react(username: str, emoji: str = _DEFAULT_EMOJI) -> dict:
    tgt = resolve_target(username)
    if tgt is None:
        return {"ok": False, "reason": f"couldn't find a message from @{username}"}
    try:
        get_client().add_reaction(tgt["message_id"], emoji or _DEFAULT_EMOJI)
    except TodyError as exc:
        return {"ok": False, "reason": f"tody error: {exc}"}
    log_event("tody_social_react", risk_tier="medium",
              detail=f"user=@{tgt['username']}; msg={tgt['message_id']}; {emoji}")
    return {"ok": True, "username": tgt["username"], "emoji": emoji,
            "message_id": tgt["message_id"]}


def do_reply(username: str, body: str) -> dict:
    tgt = resolve_target(username)
    if tgt is None:
        return {"ok": False, "reason": f"couldn't find a message from @{username}"}
    text = (body or "").strip()
    if not text:
        return {"ok": False, "reason": "empty reply"}
    try:
        get_client().reply(tgt["conversation_id"], tgt["message_id"], text)
    except TodyError as exc:
        return {"ok": False, "reason": f"tody error: {exc}"}
    log_event("tody_social_reply", risk_tier="high",
              detail=f"user=@{tgt['username']}; conv={tgt['conversation_id']}")
    return {"ok": True, "username": tgt["username"], "body": text}


def do_star(username: str) -> dict:
    tgt = resolve_target(username)
    if tgt is None:
        return {"ok": False, "reason": f"couldn't find a message from @{username}"}
    try:
        get_client().star(tgt["message_id"], True)
    except TodyError as exc:
        return {"ok": False, "reason": f"tody error: {exc}"}
    log_event("tody_social_star", risk_tier="low",
              detail=f"user=@{tgt['username']}; msg={tgt['message_id']}")
    return {"ok": True, "username": tgt["username"], "message_id": tgt["message_id"]}


def do_post(body: str) -> dict:
    text = (body or "").strip()
    if not text:
        return {"ok": False, "reason": "empty post"}
    try:
        get_client().create_post(text)
    except TodyError as exc:
        return {"ok": False, "reason": f"tody error: {exc}"}
    log_event("tody_social_post", risk_tier="high", detail=f"len={len(text)}")
    return {"ok": True, "body": text}
