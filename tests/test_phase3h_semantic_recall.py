"""Phase 3H — semantic recall: she can find her own past.

The deepest gap: 12k+ memories, retrieval was uncapped word-overlap, never
injected into replies. She kept forgetting her own life (the @khadim denial,
reminders she "didn't remember"). This adds FTS5 relevance recall.
"""
import pytest

from app.memory import base_memory, recall_index as ri


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("SEMANTIC_RECALL_ENABLED", "true")
    from app.config import get_settings
    get_settings.cache_clear()
    # temp_db fixture gives a fresh SQLite; reset the module-level readiness.
    ri._READY = None


def _seed():
    base_memory.add(memory_type="semantic", title="ERP pricing",
                    content="Tachy School ERP costs 9999 per year flat, 21 modules",
                    project="WORK", importance_score=8)
    base_memory.add(memory_type="relationship", title="niva work",
                    content="Niva ka kaam cold calling aur demo dena hai, daily 15 calls",
                    project="WORK", related_person="niva", importance_score=6)
    base_memory.add(memory_type="belief", title="books lesson",
                    content="Rohit taught me a book is a seed not food — plant it",
                    project="PERSONAL", importance_score=9, is_permanent=True)
    base_memory.add(memory_type="procedural", title="processed:tody:135:99",
                    content="Processed inbound message 99", project="TODY")


def test_index_builds_and_reports_ready():
    _seed()
    d = ri.describe()
    assert d["fts_ready"] is True
    assert d["indexed"] >= 3


def test_recall_finds_semantically_relevant_memory():
    _seed()
    hits = ri.recall("how much does the school erp cost")
    assert hits and any("9999" in (h.content or "") for h in hits)


def test_recall_finds_hinglish_content():
    _seed()
    hits = ri.recall("niva ka kaam kya hai")
    assert any("cold calling" in (h.content or "") for h in hits)


def test_recall_skips_bookkeeping_rows():
    _seed()
    hits = ri.recall("processed inbound message", limit=10)
    assert all(not (h.content or "").startswith("Processed inbound") for h in hits)


def test_person_boost():
    _seed()
    hits = ri.recall("kaam", person="niva")
    assert hits and hits[0].related_person == "niva"


def test_recall_block_grounds_the_reply():
    _seed()
    block = ri.recall_block("book ke baare me kya seekha tha")
    assert "seed not food" in block
    assert "WHAT YOU ACTUALLY REMEMBER" in block


def test_new_memory_is_indexed_live():
    # The sync trigger must index a memory added AFTER the index was built.
    _seed()
    ri.ensure_index()
    base_memory.add(memory_type="semantic", title="fresh fact",
                    content="the capital of Bihar is Patna", project="WORK")
    hits = ri.recall("what is the capital of bihar")
    assert any("Patna" in (h.content or "") for h in hits)


def test_recall_never_raises_and_kill_switch(monkeypatch):
    _seed()
    monkeypatch.setenv("SEMANTIC_RECALL_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    assert ri.recall_block("anything") == ""
    # recall() with FTS disabled falls back to word-overlap, still no raise.
    assert isinstance(ri.recall("erp cost"), list)
