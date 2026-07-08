"""Cognitive-state spine (Phase A) — the single live state object."""
import datetime as dt
import json

from app.brain import cognitive_state as cs


def _write_state(monkeypatch, data):
    """Write the spine's own state file directly."""
    from app.config import get_settings
    path = get_settings().cognitive_state_path
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def test_prompt_block_disabled(monkeypatch):
    monkeypatch.setenv("COGNITIVE_STATE_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    assert cs.prompt_block() == ""


def test_prompt_block_fresh_brain_is_minimal(monkeypatch, tmp_path):
    # No state file, empty DB → only focus(idle) + mood(steady); no
    # commitments/inner-life/memory lines (those subsystems are empty).
    monkeypatch.setenv("COGNITIVE_STATE_PATH", str(tmp_path / "cs.json"))
    from app.config import get_settings
    get_settings.cache_clear()
    block = cs.prompt_block()
    assert "COGNITIVE STATE" in block
    assert "idle" in block
    assert "steady" in block  # default mood baseline
    assert "reminder" not in block  # no commitments
    assert "memories" not in block  # empty brain


def test_note_activity_sets_focus(monkeypatch, tmp_path):
    monkeypatch.setenv("COGNITIVE_STATE_PATH", str(tmp_path / "cs.json"))
    from app.config import get_settings
    get_settings.cache_clear()
    cs.note_activity("replying to Papa")
    block = cs.prompt_block()
    assert "replying to Papa" in block
    assert "just now" in block  # ago_min < 1


def test_focus_goes_idle_when_stale(monkeypatch, tmp_path):
    monkeypatch.setenv("COGNITIVE_STATE_PATH", str(tmp_path / "cs.json"))
    from app.config import get_settings
    get_settings.cache_clear()
    old = (dt.datetime.now(dt.UTC) - dt.timedelta(minutes=15)).isoformat()
    _write_state(monkeypatch, {"last_activity": "studying",
                               "last_activity_at": old,
                               "wake_date": "2020-01-01",
                               "awake_since": old})
    block = cs.prompt_block()
    assert "idle" in block
    assert "studying" in block  # mentions what the last activity was


def test_wake_sets_awake_since_and_shows_awake_for(monkeypatch, tmp_path):
    monkeypatch.setenv("COGNITIVE_STATE_PATH", str(tmp_path / "cs.json"))
    from app.config import get_settings
    get_settings.cache_clear()
    cs.wake()
    cs.wake()  # second wake same day keeps awake_since
    block = cs.prompt_block()
    assert "Awake for" in block
    snap = cs.snapshot()
    assert snap["awake_for"] is not None


def test_snapshot_aggregates_commitments_and_memory(monkeypatch, tmp_path):
    monkeypatch.setenv("COGNITIVE_STATE_PATH", str(tmp_path / "cs.json"))
    monkeypatch.setenv("EMOTION_MOOD_PATH", str(tmp_path / "m.json"))
    from app.config import get_settings
    get_settings.cache_clear()
    # Insert a pending scheduled action + a memory so the snapshot sees them.
    from app.db.models import CognitiveScheduledAction, CognitiveMemory, session_scope
    now = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    with session_scope() as sess:
        sess.add(CognitiveScheduledAction(conversation_id=135,
                  text="check the deploy", due_at=now + dt.timedelta(hours=2),
                  status="pending", actor="test"))
        sess.add(CognitiveMemory(memory_type="semantic", title="t", content="c"))
    snap = cs.snapshot()
    assert snap["commitments"]["count"] == 1
    assert snap["memory"]["total"] >= 1
    block = cs.prompt_block()
    assert "1 pending reminder" in block
    assert "memories" in block


def test_snapshot_fail_safe_when_subsystem_breaks(monkeypatch, tmp_path):
    monkeypatch.setenv("COGNITIVE_STATE_PATH", str(tmp_path / "cs.json"))
    from app.config import get_settings
    get_settings.cache_clear()
    import app.brain.inner_life as il
    # Break one subsystem — the spine must carry on, not crash.
    def _boom():
        raise RuntimeError("boom")
    monkeypatch.setattr(il, "describe", _boom)
    snap = cs.snapshot()
    assert snap["inner_life"] == {}  # failed read → empty, not a crash
    # prompt_block must not raise either.
    assert isinstance(cs.prompt_block(), str)


def test_prompt_block_injected_into_reply(monkeypatch, tmp_path):
    monkeypatch.setenv("COGNITIVE_STATE_PATH", str(tmp_path / "cs.json"))
    from app.config import get_settings
    get_settings.cache_clear()
    captured = {}

    class FakeProvider:
        name = "fake"

        def complete(self, system, prompt, max_tokens=800):
            captured["prompt"] = prompt
            return "ok"
    import app.brain.cognitive_loop as loop
    monkeypatch.setattr(loop, "get_provider", lambda: FakeProvider())
    # Give the spine something to say.
    cs.note_activity("replying to Papa")
    loop.process("hello Papa", channel="chat")
    assert "COGNITIVE STATE" in captured["prompt"]
    assert "replying to Papa" in captured["prompt"]
