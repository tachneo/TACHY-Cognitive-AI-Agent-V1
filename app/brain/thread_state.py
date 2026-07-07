"""Thread state — structured per-conversation working memory.

Problem from the rohitsingh chat log: Shree made promises mid-thread ("I'll
tell you when Niva replies", turn 2589) but had no structured memory of that
promise, so she couldn't follow up. dialogue_memory gives a flat last-N summary;
there's no notion of OPEN TOPICS, PENDING PROMISES, or THREAD-LOCAL PREFERENCES.

This module gives each conversation a small structured state object:
  - open_topics:    things under discussion that aren't resolved
  - promises:       things Shree (or Rohit) said they'd do, with done? flag
  - preferences:    preferences stated for THIS thread (e.g. "talk in hindi")
  - established:    facts established this thread ("Niva is my daughter")

It's derived from the recent dialogue turns + corrections, stored cheaply, and
injected into the reply context so Shree has continuity of INTENT, not just a
flat transcript. The proactive loop (Phase B) reads promises to decide what to
follow up on.
"""
from __future__ import annotations

import re

from app.memory import dialogue_memory

# ── Promise detection ────────────────────────────────────────────
# Phrases where Shree (or Rohit) commits to doing something later.
_PROMISE_SELF = re.compile(
    r"(?i)\b(?:i(?:'ll| will|'ll| shall)|main\s+(?:kar|bhej|bata|dekh|check)"
    r"|i can check|i'll check|i'll tell|i'll let you know|i'll send"
    r"|jaroor bata|bata dungi|bhej dungi|dekh leti|check kar leti)\b")
_PROMISE_OTHER = re.compile(
    r"(?i)\b(?:you(?:'ll| will| should| can)|tum\s+(?:kar|bhej|bata|dekh)|"
    r"tumhe\s+(?:karna|bhejna|batana))\b")

# Topics: noun-ish phrases worth tracking. Conservative — we keep the message
# trimmed to a few words as the "topic", not a full parse.
_TOPIC_STOP = {"the", "a", "an", "is", "are", "was", "were", "i", "you", "me",
               "to", "of", "and", "or", "for", "on", "in", "at", "kya", "ho",
               "hai", "ko", "se", "ne", "ki", "ka", "ke", "aur", "ya", "to",
               "bhi", "hi", "tha", "the", "ab", "abhi", "ye", "vo", "wo",
               "yeh", "woh", "kuch", "bahut", "thoda", "sab"}


def _extract_promise(text: str) -> str | None:
    if _PROMISE_SELF.search(text or ""):
        # Take the clause containing the promise verb.
        m = _PROMISE_SELF.search(text)
        tail = text[m.start():m.start() + 120].strip()
        return tail[:120]
    return None


def _extract_topic(text: str) -> str | None:
    words = re.findall(r"[A-Za-z\u0900-\u097F]{3,}", text or "")
    keep = [w for w in words if w.lower() not in _TOPIC_STOP][:4]
    return " ".join(keep) if keep else None


def _load_state(conversation_id: int | str) -> dict:
    """Rebuild thread state from the recent dialogue turns (cheap, no extra
    storage). Returns {open_topics, promises, established}."""
    turns = dialogue_memory.recall_dialogue(conversation_id, limit=20)
    topics: list[str] = []
    promises: list[dict] = []
    established: list[str] = []
    for t in turns:
        title = t.get("title", "")
        body = t.get("content", "") or ""
        direction = "outbound" if ("outbound" in title) else "inbound"
        # promises Shree made in her own replies
        p = _extract_promise(body)
        if p and direction == "outbound":
            promises.append({"who": "shree", "text": p, "done": False})
        # topics (deduped, last 3)
        tp = _extract_topic(body)
        if tp and tp not in topics:
            topics.append(tp)
    # keep only recent topics
    return {
        "open_topics": topics[-3:],
        "promises": promises[-4:],
        "established": established,
    }


def thread_context_block(conversation_id: int | str) -> str:
    """A prompt block summarizing the thread's open state, so Shree has
    continuity of intent — she knows what she promised and what's unresolved."""
    st = _load_state(conversation_id)
    lines: list[str] = []
    if st["open_topics"]:
        lines.append("Open topics in this thread: "
                     + "; ".join(st["open_topics"]))
    open_promises = [p for p in st["promises"] if not p["done"]
                     and p["who"] == "shree"]
    if open_promises:
        lines.append("Your own UNFINISHED promises in this thread (follow up "
                     "if the relevant thing happened):")
        for p in open_promises:
            lines.append(f"  - you said: \"{p['text'][:80]}\"")
    if not lines:
        return ""
    return ("THREAD STATE (what's open in THIS conversation):\n"
            + "\n".join(lines) + "\n\n")


def open_promises(conversation_id: int | str) -> list[dict]:
    """Shree's unfinished promises in a conversation — used by the proactive
    loop (Phase B) to decide what to follow up on."""
    return [p for p in _load_state(conversation_id)["promises"]
            if not p["done"] and p["who"] == "shree"]
