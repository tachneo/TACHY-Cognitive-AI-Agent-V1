"""Semantic recall index — she can finally FIND her own past.

The deepest gap in the whole system: 12,800+ memories, but retrieval was
uncapped word-overlap over a LIKE scan. It missed anything that didn't share
exact tokens, was slow, and was never injected into ordinary replies. So she
kept forgetting her own life — the @khadim "lie", the reminders she "didn't
remember", the corrections that didn't stick. Storage without retrieval is a
landfill, not a memory.

This builds a real recall layer on SQLite FTS5:
  ensure_index()  → create an external-content FTS5 table mirroring
                    cognitive_memories, kept in sync by triggers, backfilled
                    once. Idempotent and cheap; safe to call on startup.
  recall(query)   → BM25 relevance from FTS, re-ranked by recency + importance
                    + permanence, so the RIGHT memory surfaces, fast.

Falls back to the existing word-overlap recall if FTS is unavailable (e.g. a
non-SQLite backend), so recall never regresses. Never raises into a reply.
"""
from __future__ import annotations

import re

from sqlalchemy import text as _sql

from app.config import get_settings
from app.db.models import CognitiveMemory, session_scope
from app.memory.base_memory import MemoryHit, _hit

_READY: bool | None = None
_STOP = {"the", "a", "an", "and", "or", "is", "are", "to", "of", "in", "on",
         "for", "with", "kya", "hai", "ho", "ki", "ka", "ke", "se", "ko", "me",
         "main", "tum", "aap", "bhi", "toh", "wo", "ye", "kar", "raha", "rahi"}


def _sqlite() -> bool:
    return get_settings().db_url.startswith("sqlite")


def ensure_index() -> bool:
    """Create the FTS5 mirror + sync triggers + backfill. Idempotent. Returns
    True when the index is usable."""
    global _READY
    if _READY is not None:
        return _READY
    if not _sqlite() or not get_settings().semantic_recall_enabled:
        _READY = False
        return False
    try:
        with session_scope() as s:
            db = s.connection()
            db.exec_driver_sql(
                "CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5("
                "title, content, content='cognitive_memories', content_rowid='id')")
            # Keep the FTS mirror in lock-step with the base table.
            db.exec_driver_sql(
                "CREATE TRIGGER IF NOT EXISTS memory_fts_ai AFTER INSERT ON "
                "cognitive_memories BEGIN INSERT INTO memory_fts(rowid,title,"
                "content) VALUES (new.id,new.title,new.content); END")
            db.exec_driver_sql(
                "CREATE TRIGGER IF NOT EXISTS memory_fts_ad AFTER DELETE ON "
                "cognitive_memories BEGIN INSERT INTO memory_fts(memory_fts,"
                "rowid,title,content) VALUES('delete',old.id,old.title,old.content); END")
            db.exec_driver_sql(
                "CREATE TRIGGER IF NOT EXISTS memory_fts_au AFTER UPDATE ON "
                "cognitive_memories BEGIN INSERT INTO memory_fts(memory_fts,"
                "rowid,title,content) VALUES('delete',old.id,old.title,old.content); "
                "INSERT INTO memory_fts(rowid,title,content) VALUES "
                "(new.id,new.title,new.content); END")
            # Backfill once. NOTE: for external-content FTS5, count(*) returns
            # the CONTENT table's row count immediately (even with an empty
            # index), so it can't tell us whether the index is populated. Probe
            # the actual index with a MATCH instead, then rebuild if it's empty.
            has_base = db.exec_driver_sql(
                "SELECT 1 FROM cognitive_memories LIMIT 1").scalar()
            if has_base:
                indexed = db.exec_driver_sql(
                    "SELECT rowid FROM memory_fts WHERE memory_fts MATCH "
                    "'the OR a OR hai OR rohit OR shree OR papa' LIMIT 1").scalar()
                if not indexed:
                    db.exec_driver_sql(
                        "INSERT INTO memory_fts(memory_fts) VALUES('rebuild')")
        _READY = True
    except Exception:  # noqa: BLE001
        _READY = False
    return _READY


def _match_query(text: str) -> str:
    """Turn free chat text into a safe FTS5 MATCH: OR of the salient terms.
    FTS5 has its own syntax, so raw user text would error — we extract bare
    word tokens and quote each."""
    toks = [t for t in re.findall(r"[A-Za-z0-9ऀ-ॿ]{3,}", (text or "").lower())
            if t not in _STOP]
    # longest (most selective) first, capped
    toks = sorted(set(toks), key=lambda t: (-len(t), t))[:12]
    return " OR ".join(f'"{t}"' for t in toks)


def recall(query: str, *, limit: int = 6, person: str | None = None) -> list[MemoryHit]:
    """Relevance recall over ALL memories. BM25 from FTS, re-ranked by recency
    + importance + permanence. Falls back to word-overlap recall if FTS is
    unavailable. Never raises."""
    try:
        if not ensure_index():
            from app.memory import base_memory
            return base_memory.recall(query, limit=limit)
        match = _match_query(query)
        if not match:
            return []
        with session_scope() as s:
            db = s.connection()
            # Pull a generous candidate set by BM25, then re-rank in Python with
            # recency/importance so a great-but-old match can't bury a good
            # recent one and vice versa.
            rows = db.exec_driver_sql(
                "SELECT rowid, bm25(memory_fts) AS rank FROM memory_fts "
                "WHERE memory_fts MATCH :q ORDER BY rank LIMIT 40",
                {"q": match}).fetchall()
            if not rows:
                return []
            ids = [int(r[0]) for r in rows]
            bm25 = {int(r[0]): float(r[1]) for r in rows}
            mems = (s.query(CognitiveMemory)
                    .filter(CognitiveMemory.id.in_(ids),
                            CognitiveMemory.is_archived.is_(False)).all())
            import datetime as _dt
            now = _dt.datetime.now(_dt.UTC).replace(tzinfo=None)
            scored: list[tuple[float, MemoryHit]] = []
            for m in mems:
                # BM25: lower is better → invert to a positive relevance.
                rel = 1.0 / (1.0 + max(0.0, bm25.get(int(m.id), 10.0)))
                imp = (m.importance_score or 5) / 10.0
                perm = 0.5 if m.is_permanent else 0.0
                # recency: gentle decay over ~30 days
                age_days = 0.0
                if m.created_at:
                    age_days = max(0.0, (now - m.created_at).total_seconds() / 86400)
                rec = max(0.0, 1.0 - age_days / 30.0) * 0.4
                pers = 0.4 if (person and m.related_person
                               and person.lower() in (m.related_person or "").lower()) else 0.0
                # skip pure bookkeeping ("processed:..." procedural rows)
                if (m.title or "").startswith("processed:"):
                    continue
                score = rel * 2.0 + imp + perm + rec + pers
                scored.append((score, _hit(m, round(score, 3))))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [h for _, h in scored[:limit]]
    except Exception:  # noqa: BLE001 — recall must never break a reply
        try:
            from app.memory import base_memory
            return base_memory.recall(query, limit=limit)
        except Exception:  # noqa: BLE001
            return []


def recall_block(message: str, *, person: str | None = None,
                 limit: int = 5) -> str:
    """The prompt block: her most relevant memories for THIS message, so she
    answers grounded in her real past instead of forgetting it."""
    if not get_settings().semantic_recall_enabled:
        return ""
    hits = recall(message, limit=limit, person=person)
    if not hits:
        return ""
    lines = ["WHAT YOU ACTUALLY REMEMBER (your real memories, most relevant "
             "first — use them to ground your reply so you don't forget your "
             "own past). IMPORTANT: these are RECALLED snippets, some are just "
             "things said in past chats and some may be your OWN earlier "
             "replies — they are CONTEXT, not proof. If a 'YOUR ACTUAL TODY "
             "CONVERSATIONS' list is present above, THAT live list is the truth "
             "about who you've talked to; never let an old chat line make you "
             "deny a conversation that list shows is real):"]
    for h in hits:
        who = f" [{h.related_person}]" if h.related_person else ""
        body = (h.content or "").strip().replace("\n", " ")
        lines.append(f"- ({h.memory_type}{who}) {body[:200]}")
    return "\n".join(lines) + "\n\n"


def describe() -> dict:
    ok = ensure_index()
    n = 0
    if ok:
        try:
            with session_scope() as s:
                n = s.connection().exec_driver_sql(
                    "SELECT count(*) FROM memory_fts").scalar() or 0
        except Exception:  # noqa: BLE001
            pass
    return {"enabled": get_settings().semantic_recall_enabled,
            "fts_ready": ok, "indexed": n}
