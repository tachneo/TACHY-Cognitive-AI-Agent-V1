"""Hindi/Hinglish/English grammar signals for chat understanding.

This is deliberately deterministic. The LLM may help with nuance later, but
basic grammar must not depend on a model: tense, person, time scope, @targets,
and common Indian chat instructions should be reliable before any action runs.
"""
from __future__ import annotations

import re

_DEVANAGARI = re.compile(r"[\u0900-\u097f]")
_HINGLISH = re.compile(
    r"\b(?:kya|kaise|kaisi|kisi|kyu|kyun|tum|tumne|tumhe|mujhe|maine|mera|"
    r"kar|karo|kiya|raha|rahi|rahe|tha|thi|the|hai|ho|haan|nahi|aaj|kal|"
    r"parso|kabhi|usse|usko|unko|pucho|puchho|bolo|bhejo|banao|padhai)\b",
    re.I,
)

_TARGET_AT = re.compile(r"@([A-Za-z0-9_.]{2,40})")
_TARGET_CASE = re.compile(
    r"\b([A-Za-z0-9_.]{2,40})\s+(?:ko|se)\b",
    re.I,
)
_TARGET_EN = re.compile(
    r"\b(?:talk\s+to|chat\s+with|message|msg|text|tell|inform|reply\s+to)\s+@?([A-Za-z0-9_.]{2,40})\b",
    re.I,
)
_CONNECTOR_WORDS = {"or", "aur", "and", "ya", "to"}
_PRONOUN_STOP = {
    "main", "maine", "mujhe", "mera", "meri", "mere", "i", "me", "my",
    "tum", "tu", "tujhe", "tumhe", "tera", "teri", "aap", "aapko", "you",
    "us", "usse", "usko", "unko", "unhe", "wo", "woh", "they", "he", "she",
    "koi", "sab", "sabko", "dono", "papa", "rohit", *_CONNECTOR_WORDS,
    "message", "msg", "text", "karo", "kar", "bhejo", "bolo", "batao",
    "pucho", "puchho", "baat", "haal", "chaal", "padhai",
}

_FIRST = re.compile(r"\b(?:main|maine|mujhe|mera|meri|mere|i|me|my|hum|ham)\b", re.I)
_SECOND = re.compile(r"\b(?:tum|tumne|tumhe|tu|tujhe|tera|teri|aap|aapko|you|your)\b", re.I)
_THIRD = re.compile(r"@\w+|\b(?:usne|usse|usko|unko|unhe|wo|woh|they|them|he|she|niva|khalid)\b", re.I)
_PRONOUN_REF = re.compile(r"\b(?:usse|usko|unko|unhe|usne|wo|woh|they|them|he|she|her|him)\b", re.I)

_PAST = re.compile(r"\b(?:kiya|hua|ho gaya|kha liya|tha|thi|the|did|done|sent|bheja|baat hui|karti thi)\b", re.I)
_PRESENT = re.compile(r"\b(?:kar raha|kar rahi|kar rahe|ho raha|chal rahi|chal raha|hai|hoon|hun|am|is|are|now|abhi|karo|pucho|puchho|bolo|banao)\b", re.I)
_FUTURE = re.compile(r"\b(?:karunga|karungi|karegi|karega|karenge|hoga|hog[ai]|will|tomorrow|kal\s+(?:kar|aana|bhej|call)|baad|later)\b", re.I)

_EVER = re.compile(r"\b(?:kabhi|ever|anytime|any time|ab tak|pehle)\b", re.I)
_PAST_2 = re.compile(r"\b(?:kal\s+ya\s+parso|kal\s+or\s+parso|yesterday\s+or\s+day before)\b", re.I)
_PARSO = re.compile(r"\b(?:parso|परसों|day before yesterday)\b", re.I)
_KAL = re.compile(r"\b(?:kal|कल|yesterday)\b", re.I)
_TODAY = re.compile(r"\b(?:aaj|आज|today|abhi|right now|is din)\b", re.I)

_LEADING_CONNECTOR = re.compile(
    r"^\s*(?:(?:or|aur|and|ya)\s+)?(?:(?:usse|usko|unko|unhe|isko|inhe|"
    r"him|her|them)\s+)?(?:ki|that\s+)?",
    re.I,
)


def detect_language(text: str) -> str:
    if _DEVANAGARI.search(text or ""):
        return "hindi_devanagari"
    if _HINGLISH.search(text or ""):
        return "hinglish"
    return "english"


def detect_temporal_scope(text: str) -> str:
    lower = text or ""
    if _EVER.search(lower):
        return "all_time"
    if _PAST_2.search(lower):
        return "past_2_days"
    if _PARSO.search(lower):
        return "day_before_yesterday"
    if _KAL.search(lower):
        return "yesterday_or_tomorrow"
    if _TODAY.search(lower):
        return "today"
    return "unspecified"


def detect_tense(text: str) -> str:
    hits = []
    if _PAST.search(text or ""):
        hits.append("past")
    if _PRESENT.search(text or ""):
        hits.append("present")
    if _FUTURE.search(text or ""):
        hits.append("future")
    if not hits:
        return "unknown"
    return hits[0] if len(hits) == 1 else "mixed"


def detect_person(text: str) -> str:
    hits = []
    if _FIRST.search(text or ""):
        hits.append("first")
    if _SECOND.search(text or ""):
        hits.append("second")
    if _THIRD.search(text or ""):
        hits.append("third")
    if not hits:
        return "unknown"
    return hits[0] if len(hits) == 1 else "mixed"


def extract_targets(text: str) -> list[str]:
    out: list[str] = []
    for rx in (_TARGET_AT, _TARGET_CASE, _TARGET_EN):
        for m in rx.finditer(text or ""):
            name = (m.group(1) or "").strip().lstrip("@").lower()
            if not name or name in _PRONOUN_STOP:
                continue
            if name not in out:
                out.append(name)
    return out


def has_person_pronoun(text: str) -> bool:
    return bool(_PRONOUN_REF.search(text or ""))


def resolve_recent_person(text: str, recent_texts: list[str]) -> str | None:
    """Resolve `usse/usko/wo/her` to the latest explicit target in recent turns."""
    explicit = extract_targets(text)
    if explicit:
        return explicit[0]
    if not has_person_pronoun(text):
        return None
    for item in reversed(recent_texts[-12:]):
        targets = extract_targets(item)
        if targets:
            return targets[-1]
    return None


def clean_recipient_body(text: str) -> str:
    """Remove Hinglish connector/pronoun residue from a message body.

    Example: "or usse haal chaal pucho" -> "haal chaal pucho".
    """
    body = _LEADING_CONNECTOR.sub("", text or "").strip(" :,-\n")
    return re.sub(r"\s+", " ", body).strip()


def naturalize_recipient_instruction(body: str) -> str:
    """Convert common Indian chat instructions into text safe to send."""
    cleaned = clean_recipient_body(body)
    low = cleaned.casefold()
    if "haal" in low and "chaal" in low:
        tail = " Sab thik hai na?" if "thik" in low or "theek" in low else ""
        return f"Hii, kaise ho?{tail}".strip()
    if "sab thik" in low or "sab theek" in low:
        return "Hii, kaise ho? Sab thik hai na?"
    if "padhai" in low and ("kaisi" in low or "kisi" in low or "chal" in low):
        return "Hii, padhai kaisi chal rahi hai?"
    return cleaned


def analyze(text: str) -> dict:
    return {
        "language": detect_language(text),
        "tense": detect_tense(text),
        "person": detect_person(text),
        "temporal_scope": detect_temporal_scope(text),
        "targets": extract_targets(text),
    }
