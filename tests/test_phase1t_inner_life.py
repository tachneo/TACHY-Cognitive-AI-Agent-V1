"""Phase 1T — Inner Life: self-thinking, continuous learning, sharing (hermetic)."""
import datetime as dt

import pytest

from app.brain import inner_life


@pytest.fixture(autouse=True)
def fresh_settings():
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _ist(hour: int) -> dt.datetime:
    tz = dt.timezone(dt.timedelta(hours=5, minutes=30))
    return dt.datetime(2026, 7, 3, hour, 0, tzinfo=tz)


# ── Thinking ────────────────────────────────────────────────────

def test_think_stores_belief_memory_and_advances_seed():
    out = inner_life.think()
    assert out["enabled"] is True
    assert out["memory_id"]
    from app.memory import base_memory
    hits = base_memory.search(memory_type="belief", project="INNER_LIFE")
    assert hits and "Inner thought" in hits[0].title
    # seed rotation advanced
    assert inner_life._load_state()["seed_index"] == 1


def test_think_parses_question_and_share(monkeypatch):
    class FakeProvider:
        name = "fake"

        def complete(self, system, prompt, max_tokens=400):
            return ("THOUGHT: I connected the ERP fee dedup lesson to TODY "
                    "payments; the same double-count risk exists there.\n"
                    "QUESTION: How do payment apps prevent duplicate webhooks?\n"
                    "SHARE: I was thinking about duplicate payment webhooks — "
                    "TODY may have the same risk we fixed in the ERP. Worth a "
                    "look together?")

    monkeypatch.setattr(inner_life, "get_provider", lambda: FakeProvider())
    out = inner_life.think("memory")
    assert "duplicate webhooks" in out["question"]
    assert out["share_queued"] is True
    state = inner_life._load_state()
    assert state["curiosity_queue"] and state["share_queue"]


def test_think_handles_none_sections(monkeypatch):
    class FakeProvider:
        name = "fake"

        def complete(self, system, prompt, max_tokens=400):
            return "THOUGHT: Just a quiet reflection.\nQUESTION: NONE\nSHARE: NONE"

    monkeypatch.setattr(inner_life, "get_provider", lambda: FakeProvider())
    out = inner_life.think("mood")
    assert out["question"] is None
    assert out["share_queued"] is False


# ── Continuous learning from own questions ──────────────────────

def test_mini_learn_uses_curiosity_queue_first(monkeypatch):
    state = inner_life._load_state()
    state["curiosity_queue"] = ["how do payment apps prevent duplicate webhooks"]
    inner_life._save_state(state)
    captured = {}

    def fake_explore(topic=None, **kw):
        captured["topic"] = topic
        return {"topic": topic, "learned": True}

    from app.brain import web_learning
    monkeypatch.setattr(web_learning, "explore", fake_explore)
    out = inner_life.mini_learn()
    assert "webhooks" in captured["topic"]
    assert out["learned"] is True
    assert inner_life._load_state()["curiosity_queue"] == []


# ── Sharing: circadian gate + daily cap ─────────────────────────

def _queue_share(text="I learned something interesting today."):
    state = inner_life._load_state()
    state["share_queue"].append(text)
    inner_life._save_state(state)


def test_share_respects_waking_hours():
    _queue_share()
    night = inner_life.maybe_share(now=_ist(2))
    assert night["share"] is None and "hours" in night["reason"]
    day = inner_life.maybe_share(now=_ist(10))
    assert day["share"]


def test_share_daily_cap():
    for _ in range(5):
        _queue_share()
    sent = [inner_life.maybe_share(now=_ist(11))["share"] for _ in range(5)]
    assert sum(1 for s in sent if s) == 3  # inner_life_share_cap default


# ── Consolidation ───────────────────────────────────────────────

def test_consolidate_creates_lesson_and_archives_stale():
    import datetime as dtm

    from app.db.models import CognitiveMemory, session_scope
    from app.memory import base_memory

    mid = base_memory.add(memory_type="episodic", title="stale trivia",
                          content="x", importance_score=3)
    keep = base_memory.add(memory_type="episodic", title="important",
                           content="y", importance_score=9)
    with session_scope() as s:
        s.get(CognitiveMemory, mid).created_at = \
            dtm.datetime.now(dtm.UTC).replace(tzinfo=None) - dtm.timedelta(days=30)
    out = inner_life.consolidate()
    assert out["lesson_id"] and out["archived"] >= 1
    with session_scope() as s:
        assert s.get(CognitiveMemory, mid).is_archived is True
        assert s.get(CognitiveMemory, keep).is_archived is False
    hits = base_memory.search(memory_type="semantic", project="INNER_LIFE")
    assert hits and "consolidation" in hits[0].title.lower()


# ── Rhythm + kill switch ────────────────────────────────────────

def test_tick_runs_think_first_then_learn(monkeypatch):
    monkeypatch.setattr(inner_life, "think", lambda seed=None: {"ok": "think"})
    monkeypatch.setattr(inner_life, "mini_learn", lambda: {"ok": "learn"})
    ran = inner_life.tick(now=_ist(12))
    assert "think" in ran and "learn" not in ran
    # after think ran, next tick within think-interval triggers learn
    state = inner_life._load_state()
    state["last_think"] = _ist(12).isoformat()
    inner_life._save_state(state)
    ran2 = inner_life.tick(now=_ist(12))
    assert "learn" in ran2 and "think" not in ran2


def test_tick_consolidates_in_early_morning(monkeypatch):
    monkeypatch.setattr(inner_life, "think", lambda seed=None: {})
    monkeypatch.setattr(inner_life, "mini_learn", lambda: {})
    monkeypatch.setattr(inner_life, "consolidate", lambda: {"ok": True})
    ran = inner_life.tick(now=_ist(4))
    assert "consolidate" in ran
    # already done today → not again
    ran2 = inner_life.tick(now=_ist(5))
    assert "consolidate" not in ran2


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("INNER_LIFE_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    assert inner_life.tick() == {"enabled": False}
    assert inner_life.think() == {"enabled": False}


def test_inner_routes_mounted():
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as client:
        resp = client.get("/inner/state")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert "recent_thoughts" in body and "mood" in body
