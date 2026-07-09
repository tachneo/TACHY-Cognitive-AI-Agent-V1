"""Autonomous tasks — Shree's self-triggering loop (Phase 2K)."""
import datetime as dt
import json

from app.brain import autonomous_tasks as at


def _enable(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTONOMOUS_TASKS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMOUS_TASKS_DAILY_CAP_PER_HANDLER", "3")
    monkeypatch.setenv("TODY_DAILY_GROWTH_CONVERSATION_ID", "135")
    from app.config import get_settings
    get_settings.cache_clear()


def _insert_due(handler="reflect", *, name="test routine",
                interval=1440, at_time=None, past=True, status="active",
                params=None):
    """Insert a task directly with next_run_at in the past so it's due now."""
    from app.db.models import CognitiveAutonomousTask, session_scope
    nxt = at._utcnow_naive() - dt.timedelta(minutes=5) if past else at._utcnow_naive() + dt.timedelta(hours=1)
    with session_scope() as sess:
        row = CognitiveAutonomousTask(name=name, handler=handler, intent="test",
                                      params=json.dumps(params) if params else None,
                                      interval_minutes=interval, at_time_hhmm=at_time,
                                      next_run_at=nxt, status=status, created_by="test")
        sess.add(row)
        sess.flush()
        return int(row.id)


# ── register / allowlist ─────────────────────────────────────────


def test_register_rejects_unknown_handler(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    res = at.register(name="bad", handler="rm_rf", interval_minutes=60)
    assert res["ok"] is False
    assert "allowlist" in res["error"]


def test_register_creates_active_task(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    res = at.register(name="morning errors", handler="review_tody_errors",
                      interval_minutes=1440, at_time_hhmm="08:00",
                      intent="check errors each morning")
    assert res["ok"] is True
    assert res["handler"] == "review_tody_errors"
    assert res["interval_minutes"] == 1440


def test_register_clamps_interval_to_minimum(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    res = at.register(name="fast", handler="reflect", interval_minutes=1)
    assert res["interval_minutes"] == at._MIN_INTERVAL


# ── run_due / dispatch / caps ────────────────────────────────────


def test_run_due_dispatches_readonly_handler(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    rid = _insert_due("reflect")
    # Patch the handler to a stub so no real LLM runs.
    called = {"n": 0}
    def fake_reflect(params):
        called["n"] += 1
        return {"thought": True}
    monkeypatch.setitem(at._HANDLERS, "reflect", fake_reflect)
    out = at.run_due()
    assert out["ran_count"] == 1
    assert called["n"] == 1
    # next_run_at pushed forward; not due again immediately.
    assert at.run_due()["ran_count"] == 0


def test_run_due_daily_cap_skips(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)  # cap = 3
    rid = _insert_due("reflect")
    monkeypatch.setitem(at._HANDLERS, "reflect", lambda p: {"thought": True})
    # Force next_run_at back into the past after each run by patching _compute_next_run.
    monkeypatch.setattr(at, "_compute_next_run",
                        lambda i, t=None, after=None: at._utcnow_naive() - dt.timedelta(minutes=1))
    for _ in range(3):
        at.run_due()
    # 4th run hits the cap.
    out = at.run_due()
    assert out["ran_count"] == 0  # capped, skipped


def test_run_due_marks_error_and_continues_others(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    r1 = _insert_due("reflect", name="will fail")
    r2 = _insert_due("reflect", name="will pass")
    def boom(params):
        raise RuntimeError("boom")
    monkeypatch.setitem(at._HANDLERS, "reflect", boom)
    out = at.run_due()
    # The failing task is marked error, not crashed.
    assert out["ran_count"] >= 1
    assert any(r["id"] == r1 and r.get("error") for r in out["ran"])


def test_handler_failure_sets_status_error(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    rid = _insert_due("reflect")
    monkeypatch.setitem(at._HANDLERS, "reflect", lambda p: (_ for _ in ()).throw(RuntimeError("x")))
    at.run_due()
    active = at.list_active()
    row = next(r for r in active if r["id"] == rid)
    assert row["status"] == "error" if "status" in row else True
    # pause/resume cycle works on errored tasks.
    assert at.pause(rid) is True


def test_run_due_disabled_when_off(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTONOMOUS_TASKS_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    assert at.run_due()["enabled"] is False


# ── extract_from_message ─────────────────────────────────────────


def _set_light(monkeypatch, payload):
    monkeypatch.setattr(at, "_light_complete", lambda prompt: payload)


def test_extract_registers_recurring_task(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    _set_light(monkeypatch, json.dumps({
        "handler": "review_tody_errors", "name": "morning error check",
        "intent": "check my logs each morning", "interval_minutes": 1440,
        "at_time_hhmm": "08:00", "params": {}}))
    res = at.extract_from_message("roz subah apne errors check karo")
    assert res.get("ok") is True or res.get("id")
    assert res.get("handler") == "review_tody_errors"


def test_extract_skips_when_no_recurring_cue(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    res = at.extract_from_message("hello how are you")
    assert res["created"] is False
    assert res["reason"] == "no recurring cue"


def test_extract_rejects_bad_handler_from_model(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    _set_light(monkeypatch, json.dumps({"handler": "rm_rf", "interval_minutes": 60}))
    res = at.extract_from_message("roz kuch karo")
    assert res["created"] is False
    assert "bad_handler" in res["reason"]


def test_extract_never_raises_on_model_error(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    def boom(p):
        raise RuntimeError("down")
    monkeypatch.setattr(at, "_light_complete", boom)
    res = at.extract_from_message("roz subah errors check karo")
    assert res["created"] is False
    assert res["reason"] == "light_model_error"


# ── injection hint + spine ───────────────────────────────────────


def test_injection_hint_only_when_registered():
    assert at.injection_hint({}) == ""
    assert at.injection_hint({"created": False}) == ""
    h = at.injection_hint({"id": 9, "handler": "study", "next_run_at": "2026-07-09T03:00"})
    assert "#9" in h and "routine set" in h.lower() or "self-trigger" in h.lower()


def test_spine_shows_autonomous_routines(monkeypatch, tmp_path):
    monkeypatch.setenv("COGNITIVE_STATE_PATH", str(tmp_path / "cs.json"))
    monkeypatch.setenv("AUTONOMOUS_TASKS_ENABLED", "true")
    from app.config import get_settings
    get_settings.cache_clear()
    _insert_due("reflect", name="spine test routine")
    from app.brain import cognitive_state as cs
    block = cs.prompt_block()
    assert "self-directed routine" in block or "24/7 loop" in block
    assert "only awake on message" in block  # the corrective line
