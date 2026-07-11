"""Prospective memory — the scheduler (Phase 2K).

Shree converts from talking about the future to acting in it: the light model
extracts a time-bound commitment from an inbound guardian message, a
scheduled_actions row is written, the worker fires it through the approval-gated
send when due, and the reply may honestly say "reminder set" only because the
row exists.
"""
import datetime as dt

from app.llm import gen_state
from app.brain import prospective_memory as pm


def _set_light(monkeypatch, json_or_none):
    """Make the light model return a fixed JSON string (or None for a failure)."""
    def fake_complete(prompt):
        return json_or_none if json_or_none is not None else ""
    monkeypatch.setattr(pm, "_light_complete", fake_complete)


def _due_json(monkeypatch, due_ist, text="ping about the deploy", confidence=0.9):
    _set_light(monkeypatch, f'{{"due_at": "{due_ist}", "text": "{text}", "confidence": {confidence}}}')


def test_extract_creates_row_for_time_bound_commitment(monkeypatch):
    now = dt.datetime.now(pm._IST)
    soon = (now + dt.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")
    _due_json(monkeypatch, soon)

    res = pm.extract("remind me to check the deploy at " + soon,
                     135, source_message_id=42, person="Rohit Kumar",
                     is_guardian=True)

    assert res["created"] is True
    assert "id" in res
    due = dt.datetime.fromisoformat(res["due_at_utc"])
    assert due > dt.datetime.now(dt.UTC).replace(tzinfo=None) - dt.timedelta(minutes=1)


def test_extract_skips_non_guardian(monkeypatch):
    _due_json(monkeypatch, "2099-01-01 10:00")
    res = pm.extract("remind me tomorrow", 135, is_guardian=False)
    assert res["created"] is False
    assert res["reason"] == "non-guardian"


def test_extract_disabled_when_killed(monkeypatch):
    monkeypatch.setenv("PROSPECTIVE_MEMORY_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    _due_json(monkeypatch, "2099-01-01 10:00")
    res = pm.extract("remind me tomorrow at 5", 135, is_guardian=True)
    assert res["created"] is False
    assert res["reason"] == "disabled"
    monkeypatch.setenv("PROSPECTIVE_MEMORY_ENABLED", "true")
    get_settings.cache_clear()


def test_extract_skips_when_no_future_cue(monkeypatch):
    # No future cue → no model call even made.
    res = pm.extract("hello how are you", 135, is_guardian=True)
    assert res["created"] is False
    assert res["reason"] == "no future cue"


def test_extract_skips_when_model_says_no_commitment(monkeypatch):
    # Deterministic parser is now primary; use a message with NO parseable time
    # so it falls through to the (mocked) model, which declines.
    _set_light(monkeypatch, '{"due_at": null}')
    res = pm.extract("remind me sometime about the thing", 135, is_guardian=True)
    assert res["created"] is False
    assert res["reason"] == "no_commitment"


def test_extract_rejects_due_in_past(monkeypatch):
    # No deterministic time in the text → model path; model returns a past date.
    _due_json(monkeypatch, "2000-01-01 10:00")
    res = pm.extract("remind me about the old thing", 135, is_guardian=True)
    assert res["created"] is False
    assert res["reason"] == "due_in_past"


def test_extract_rejects_low_confidence(monkeypatch):
    now = dt.datetime.now(pm._IST)
    soon = (now + dt.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
    # No parseable time in the words → model path; model is unsure (low conf).
    _due_json(monkeypatch, soon, confidence=0.2)
    res = pm.extract("remind me about that thing later", 135, is_guardian=True)
    assert res["created"] is False
    assert res["reason"] == "low_confidence"


def test_extract_never_raises_on_model_error(monkeypatch):
    # A message with no deterministic time falls to the model; if the model
    # raises, extract must degrade gracefully (never break the reply).
    def boom(prompt):
        raise RuntimeError("model down")
    monkeypatch.setattr(pm, "_light_complete", boom)
    res = pm.extract("remind me about the thing later", 135, is_guardian=True)
    assert res["created"] is False
    assert res["reason"] == "light_model_error"


def test_injection_hint_only_when_created():
    assert pm.injection_hint({"created": False}) == ""
    hint = pm.injection_hint({"created": True, "id": 7,
                              "due_at_ist": "2026-07-09 15:00 IST",
                              "text": "ping me"})
    assert "#7" in hint and "reminder set" in hint.lower() or "ping you" in hint.lower()


def _insert_row(due_utc, text="reminder", conv=135, status="pending"):
    """Insert a scheduled action directly, bypassing extract() (which correctly
    rejects past times). For fire/list tests we need a due-in-the-past row."""
    from app.db.models import CognitiveScheduledAction, session_scope
    with session_scope() as sess:
        row = CognitiveScheduledAction(
            conversation_id=conv, text=text, due_at=due_utc,
            status=status, actor="test")
        sess.add(row)
        sess.flush()
        return int(row.id)


def test_list_due_returns_only_arrived_pending():
    now = pm._utcnow_naive()
    past_id = _insert_row(now - dt.timedelta(hours=1), text="past one")
    future_id = _insert_row(now + dt.timedelta(hours=1), text="future one")

    due = pm.list_due()
    ids = [d["id"] for d in due]
    assert past_id in ids
    assert future_id not in ids


def test_fire_due_auto_sends_and_marks_fired(monkeypatch):
    now = pm._utcnow_naive()
    rid = _insert_row(now - dt.timedelta(minutes=10), text="standalone reminder")

    # Supervised auto-reply ON → auto-approve + execute.
    monkeypatch.setenv("TODY_SUPERVISED_AUTO_REPLY", "true")
    from app.config import get_settings
    get_settings.cache_clear()

    from app.agents import tody_agent
    from app.safety import approvals

    monkeypatch.setattr(tody_agent, "request_send",
                        lambda c, b: {"queued": True, "approval": {"id": 990}})
    monkeypatch.setattr(approvals, "respond", lambda *a, **k: None)
    monkeypatch.setattr(tody_agent, "execute_send",
                        lambda aid, c, b: {"sent": True})

    result = pm.fire_due()
    assert result["fired_count"] >= 1
    fired = next(f for f in result["fired"] if f["id"] == rid)
    assert fired["sent"] is True
    assert fired["status"] == "fired"

    # The row is no longer pending → not re-fired next tick.
    assert all(f["id"] != rid for f in pm.fire_due()["fired"])


def test_fire_due_leaves_pending_approval_when_auto_reply_off(monkeypatch):
    now = pm._utcnow_naive()
    rid = _insert_row(now - dt.timedelta(minutes=30), text="manual reminder")

    monkeypatch.setenv("TODY_SUPERVISED_AUTO_REPLY", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.agents import tody_agent
    monkeypatch.setattr(tody_agent, "request_send",
                        lambda c, b: {"queued": True, "approval": {"id": 991}})
    monkeypatch.setattr(tody_agent, "execute_send",
                        lambda *a, **k: {"sent": False, "reason": "pending"})

    result = pm.fire_due()
    fired = next(f for f in result["fired"] if f["id"] == rid)
    assert fired["sent"] is False
    assert fired["status"] == "pending_approval"


def test_cancel_marks_row_cancelled():
    now = pm._utcnow_naive()
    rid = _insert_row(now + dt.timedelta(days=1), text="cancel me")
    assert pm.cancel(rid) is True
    assert rid not in [d["id"] for d in pm.list_due()]
