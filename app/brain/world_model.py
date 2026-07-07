"""World model — a lightweight relationship graph of the people in Shree's life.

Problem from the chat log: Rohit mentioned Niva is his daughter, messaged
@zarathakoo (Tehreen Thakoo), etc., but Shree couldn't connect these facts
when asked later. This module is a small, truthful world model: who the
guardian is, who his family/contacts are, and what Shree has done with them.

It is built from config (the guardian) + learned episodic memories (people
Shree has messaged or who have messaged her), never invented. The recall is
used so her replies have relational depth ("Niva is your daughter — I messaged
her last night, no reply yet") instead of blanking.
"""
from __future__ import annotations

import re

from app.config import get_settings
from app.memory import dialogue_memory, relationship_memory

# Known kinship cues in messages → relationship label.
_KINSHIP = {
    "daughter": "daughter", "beti": "daughter", "beta": "son",
    "son": "son", "wife": "wife", "patni": "wife", "biwi": "wife",
    "husband": "husband", "pati": "husband", "mother": "mother",
    "mom": "mother", "maa": "mother", "father": "father", "papa": "father",
    "baap": "father", "brother": "brother", "bhai": "brother",
    "sister": "sister", "behan": "sister", "bahan": "sister",
    "friend": "friend", "dost": "friend", "client": "client",
}

# Match ONLY @-prefixed handles (conservative — bare words cause too many false
# positives like "theek", "what", "is" being treated as people).
_HANDLE = re.compile(r"@([A-Za-z0-9_.]{2,40})")


def known_people() -> dict[str, dict]:
    """Return the world model: {display_name: {role, username, last_interaction}}.

    Seed with the guardian from config, then enrich with anyone Shree has
    recently interacted with (messaged or received from)."""
    s = get_settings()
    out: dict[str, dict] = {}
    out[s.guardian_name] = {
        "role": "guardian / father", "username": s.guardian_tody_username,
        "relation": "Papa — the one who built and teaches me",
    }
    # Anyone Shree has messaged recently → pull from dialogue memory titles.
    try:
        for turn in dialogue_memory.recall_dialogue("*", limit=40):
            title = turn.get("title", "")
            # outbound_direct titles carry the recipient name in content via
            # remember_turn(person=...); pull from related_person through search.
    except Exception:  # noqa: BLE001
        pass
    return out


def _known_person_names() -> set[str]:
    """Distinct related_person values Shree has in memory — the people she
    already knows. Used to detect name mentions without @ (Rohit often writes
    'niva' not '@niva') while avoiding false positives on ordinary words."""
    try:
        from sqlalchemy import distinct, select
        from app.db.models import CognitiveMemory, session_scope
        with session_scope() as s:
            rows = s.scalars(
                select(distinct(CognitiveMemory.related_person))
                .where(CognitiveMemory.related_person.isnot(None))
            ).all()
        return {str(r).lower() for r in rows if r}
    except Exception:  # noqa: BLE001
        return set()


def detect_mentioned_people(message: str) -> list[str]:
    """Find people mentioned in a message so we can recall their history.

    Two reliable signals (no false positives on ordinary words):
      1. @-prefixed handles ("@niva")
      2. Names of people Shree ALREADY knows from memory (related_person),
         matched case-insensitively — so 'did niva reply?' works once Niva is
         a known contact, but 'theek'/'what' never match."""
    m = (message or "").lower()
    people: list[str] = []
    for match in _HANDLE.finditer(message or ""):
        handle = match.group(1)
        if handle.lower() in {"me", "you", "him", "her", "them", "us", "papa",
                              "shree", "tody", "tachy"}:
            continue
        people.append(handle)
    known = _known_person_names()
    for name in known:
        if name and name in m:
            people.append(name)
    # dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for p in people:
        key = p.lower()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def person_facts(name: str) -> dict:
    """What Shree knows about a person: role (if kinship learned) + recent
    interactions with them (inbound from / outbound to)."""
    name = (name or "").strip()
    if not name:
        return {"name": name, "known": False}
    interactions = dialogue_memory.recall_person(name, limit=6)
    inbound = [i for i in interactions
               if "inbound" in i.get("title", "")]
    outbound = [i for i in interactions
                if "outbound" in i.get("title", "")
                or "draft_outbound" in i.get("title", "")]
    return {
        "name": name,
        "known": bool(interactions),
        "inbound_count": len(inbound),
        "outbound_count": len(outbound),
        "last_inbound": inbound[0]["content"] if inbound else None,
        "last_outbound": outbound[0]["content"] if outbound else None,
        "recent": interactions,
    }


def people_context_block(message: str) -> str:
    """A prompt block injecting what Shree knows about anyone mentioned in the
    message, so she can answer 'did Niva reply?' from fact, not blank."""
    people = detect_mentioned_people(message)
    if not people:
        return ""
    lines: list[str] = []
    for name in people[:3]:
        facts = person_facts(name)
        if not facts["known"]:
            lines.append(f"- @{name}: no past interaction I can recall. "
                         "If you've told me about them, remind me and I'll "
                         "remember.")
            continue
        parts = [f"@{name}: I have {facts['inbound_count']} message(s) from "
                 f"them and {facts['outbound_count']} from me to them."]
        if facts["last_outbound"]:
            parts.append(f"Last I sent them: \"{facts['last_outbound'][:80]}\".")
        if facts["last_inbound"]:
            parts.append(f"Last they sent me: \"{facts['last_inbound'][:80]}\".")
        else:
            parts.append("They have NOT replied yet (no inbound from them).")
        lines.append("- " + " ".join(parts))
    return ("PEOPLE YOU MENTIONED (what I actually know from memory — use this, "
            "do not say 'I don't have that' if it's here):\n"
            + "\n".join(lines) + "\n\n")
