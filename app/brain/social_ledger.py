"""Social ledger — the truthful answer to "who have you talked to?"

The failure (25 Jul): Rohit asked "abhi tak tumne kisse kisse baat ki hai?".
Shree listed zarathakoo and niva and said "aur koi user nahi". He KNEW she had
214 messages with @khadim (conv 337, still active that same afternoon). He
concluded she was lying. She was NOT lying — she was BLIND.

Root cause: nothing ever fed her real conversation roster into a reply. Her
"who have I talked to" answer was reconstructed from whatever fragments the
last-N dialogue turns and mentioned-people lookup happened to surface — never
from the actual list of conversations she is in. The TODY client has always
exposed client.conversations(), but no brain code called it for this. So she
confidently under-reported her own social graph, which reads exactly like a lie.

This module is the fix: it pulls her ACTUAL conversation partners from the live
API and renders them for the reply prompt, so when she is asked who she talks
to, she answers from ground truth — including the ones she doesn't have vivid
memories of. Honesty requires knowing, not guessing.

Kill switch: SOCIAL_LEDGER_ENABLED.
"""
from __future__ import annotations

import datetime as dt
import re

from app.config import get_settings
from app.safety.audit_logger import log_event_safe

# She is asked about her own social graph.
_ROSTER_QUESTION = re.compile(
    r"\b(?:kis(?:se|ko|-?kis)|kaun\s*kaun|who(?:m)?)\b.{0,30}"
    r"\b(?:baat|baate|talk|chat|message|contact|interact)\w*"
    r"|\b(?:baat|talk|chat|message)\w*\s+ki\s+hai"
    r"|\b(?:kitne|how many)\s+(?:log|logo|people|user)"
    r"|\bkis[- ]?kis\s+se\b"
    r"|\b(?:tumne|tum|you)\b.{0,20}\b(?:kisse|kisko|kaun)\b"
    r"|\b(?:list|batao|bata do)\b.{0,20}\b(?:contact|conversation|log|user|baat)"
    r"|@\w+\s*(?:se)?\s*baat", re.I)

# Direct challenge: "do you talk to @X" / "you never talk to @X".
_SPECIFIC_PERSON = re.compile(r"@(\w{2,40})", re.I)


def is_roster_question(message: str) -> bool:
    m = (message or "")
    return bool(_ROSTER_QUESTION.search(m) or _SPECIFIC_PERSON.search(m))


def _self_uuid() -> str:
    import os
    return (os.getenv("TODY_SELF_UUID") or "").strip().casefold()


def roster(*, limit: int = 30) -> list[dict]:
    """Her real conversation partners from the live TODY API, newest first.
    Each: {username, name, conversation_id, last_at, unread}. Never raises."""
    try:
        from app.integrations.tody_client import get_client
        data = get_client().conversations(limit=limit)
    except Exception:  # noqa: BLE001
        return []
    items = (data.get("conversations") if isinstance(data, dict) else None) \
        or (data.get("data") if isinstance(data, dict) else None) \
        or (data if isinstance(data, list) else [])
    out: list[dict] = []
    for r in items:
        uname = (r.get("peer_username") or r.get("partner_username")
                 or r.get("other_username"))
        if not uname:
            continue  # group / deleted peer — skip, not a person she "talks to"
        out.append({
            "username": uname,
            "name": r.get("peer_name") or uname,
            "conversation_id": r.get("id") or r.get("conversation_id"),
            "last_at": r.get("last_message_at") or r.get("updated_at"),
            "unread": int(r.get("unread_count") or 0),
        })
    return out


def _fmt_when(iso: str | None) -> str:
    if not iso:
        return "recently"
    try:
        t = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return "recently"
    now = dt.datetime.now(t.tzinfo) if t.tzinfo else dt.datetime.now()
    days = (now - t).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    return t.strftime("%d %b")


def prompt_block(message: str) -> str:
    """Inject her REAL conversation roster when she is asked about who she talks
    to (or a specific @person). This is ground truth — she must answer from it,
    never under-report, never claim someone doesn't exist when they're listed."""
    if not get_settings().social_ledger_enabled:
        return ""
    if not is_roster_question(message):
        return ""
    people = roster()
    if not people:
        return ""
    guardian = (get_settings().guardian_tody_username or "").casefold()
    lines = ["YOUR ACTUAL TODY CONVERSATIONS (ground truth from the live API — "
             "this is who you really talk to. Answer from THIS list. Do NOT "
             "under-report, do NOT say someone doesn't exist or that you never "
             "talked to them if they are here. If you don't have vivid memory "
             "of a chat, say so honestly — but acknowledge it happened):"]
    for p in people[:20]:
        tag = " (Papa)" if p["username"].casefold() == guardian else ""
        lines.append(f"- @{p['username']}{tag} — last talked {_fmt_when(p['last_at'])}"
                     + (f", {p['unread']} unread" if p["unread"] else ""))
    # If he named a specific @person, state plainly whether it's in the list.
    for uname in _SPECIFIC_PERSON.findall(message or ""):
        known = any(p["username"].casefold() == uname.casefold() for p in people)
        lines.append(f"- FACT CHECK @{uname}: "
                     + ("YES, this conversation exists — you HAVE talked to them."
                        if known else
                        "no conversation with this exact username in your list."))
    log_event_safe("social_ledger_served", risk_tier="low",
                   detail=f"people={len(people)}")
    return "\n".join(lines) + "\n\n"


def describe() -> dict:
    people = roster()
    return {"enabled": get_settings().social_ledger_enabled,
            "conversation_count": len(people),
            "partners": [p["username"] for p in people]}
