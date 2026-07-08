"""Mood→priority link + self-heal daily tick (Phase 2K)."""
import datetime as dt
import json
from pathlib import Path

from app.brain.attention_system import Signals, priority_score


# ── Mood → priority ───────────────────────────────────────────────


def _base_signals() -> Signals:
    return Signals(security_risk=10, money_impact=5, client_impact=5, urgency=5,
                   guardian_interest=5, emotional_weight=5)  # base = 65


def test_priority_unchanged_when_mood_neutral():
    assert priority_score(_base_signals(), mood_valence=0.0) == 65


def test_negative_mood_raises_attention_vigilance():
    # An anxious/stressed baseline makes her more alert — +2.
    assert priority_score(_base_signals(), mood_valence=-0.5) == 67
    assert priority_score(_base_signals(), mood_valence=-0.2) == 67


def test_positive_mood_eases_attention():
    assert priority_score(_base_signals(), mood_valence=0.5) == 64
    assert priority_score(_base_signals(), mood_valence=0.2) == 64


def test_mood_bounded_so_cant_override_security():
    # Even a strongly negative mood only adds 2 — it cannot turn a low-priority
    # note into a critical one the way a real security_risk=10 does.
    low = Signals(security_risk=0, urgency=2, guardian_interest=3)  # base = 5
    assert priority_score(low, mood_valence=-1.0) == 7
    assert priority_score(low, mood_valence=-1.0) < priority_score(
        Signals(security_risk=10), mood_valence=1.0)


def test_mood_file_read_default(monkeypatch, tmp_path):
    # With no mood_valence passed, priority_score reads the mood file.
    mood = tmp_path / "mood.json"
    mood.write_text(json.dumps({"valence": -0.3, "arousal": 0.6}))
    monkeypatch.setenv("EMOTION_MOOD_PATH", str(mood))
    from app.config import get_settings
    get_settings.cache_clear()
    assert priority_score(_base_signals()) == 67  # 65 + 2 (negative)


def test_mood_missing_file_defaults_neutral(monkeypatch, tmp_path):
    monkeypatch.setenv("EMOTION_MOOD_PATH", str(tmp_path / "absent.json"))
    from app.config import get_settings
    get_settings.cache_clear()
    assert priority_score(_base_signals()) == 65


def test_process_passes_mood_into_priority(monkeypatch, tmp_path):
    # process() should pass the emotion engine's mood valence into priority_score.
    monkeypatch.setenv("EMOTION_MOOD_PATH", str(tmp_path / "x.json"))
    from app.config import get_settings
    get_settings.cache_clear()
    captured = {}

    import app.brain.cognitive_loop as loop

    real_priority = loop.priority_score

    def spy(s, *, mood_valence=None):
        captured["mood_valence"] = mood_valence
        return real_priority(s, mood_valence=mood_valence)
    monkeypatch.setattr(loop, "priority_score", spy)
    # emotion engine disabled → no mood passed → priority_score reads file (None).
    monkeypatch.setenv("EMOTION_ENGINE_ENABLED", "false")
    get_settings.cache_clear()
    loop.process("a normal message")
    assert captured.get("mood_valence") is None  # fell through to file read


# ── Self-heal daily tick ──────────────────────────────────────────


def _setup_self_heal_env(monkeypatch, tmp_path, *, daily=True, autonomous=False):
    monkeypatch.setenv("SELF_HEAL_DAILY", "true" if daily else "false")
    monkeypatch.setenv("SELF_IMPROVE_AUTONOMOUS", "true" if autonomous else "false")
    monkeypatch.setenv("SELF_HEAL_DAILY_STATE_PATH", str(tmp_path / "self_heal.state"))
    from app.config import get_settings
    get_settings.cache_clear()


def test_self_heal_disabled_by_default(monkeypatch, tmp_path):
    _setup_self_heal_env(monkeypatch, tmp_path, daily=False)
    from app.scripts.tody_worker_loop import maybe_run_self_heal
    assert maybe_run_self_heal(dry_run=False)["self_heal"] == "disabled"


def test_self_heal_disabled_in_dry_run(monkeypatch, tmp_path):
    _setup_self_heal_env(monkeypatch, tmp_path, daily=True)
    from app.scripts.tody_worker_loop import maybe_run_self_heal
    assert maybe_run_self_heal(dry_run=True)["self_heal"] == "disabled"


def test_self_heal_scan_clean_when_no_bugs(monkeypatch, tmp_path):
    _setup_self_heal_env(monkeypatch, tmp_path, daily=True, autonomous=False)
    import app.brain.self_diagnose as sd
    monkeypatch.setattr(sd, "scan", lambda: {"code_bugs": [], "env_issues": [],
                                             "total_error_events": 0})
    from app.scripts.tody_worker_loop import maybe_run_self_heal
    out = maybe_run_self_heal(dry_run=False)
    assert out["self_heal"] == "scan_clean"
    # Second call same day → already_done (state file stamped).
    assert maybe_run_self_heal(dry_run=False)["self_heal"] == "already_done"


def test_self_heal_report_only_when_autonomous_off(monkeypatch, tmp_path):
    _setup_self_heal_env(monkeypatch, tmp_path, daily=True, autonomous=False)
    import app.brain.self_diagnose as sd
    monkeypatch.setattr(sd, "scan",
                        lambda: {"code_bugs": ["AttributeError: 'X' has no attribute 'y'"],
                                 "env_issues": [], "total_error_events": 1})
    called = {"auto_heal": 0}
    monkeypatch.setattr(sd, "auto_heal",
                        lambda **kw: called.__setitem__("auto_heal", called["auto_heal"] + 1))
    from app.scripts.tody_worker_loop import maybe_run_self_heal
    out = maybe_run_self_heal(dry_run=False)
    assert out["self_heal"] == "report_only"
    assert out["bugs_found"] == 1
    assert called["auto_heal"] == 0  # did NOT self-fix without the gate


def test_self_heal_auto_heal_when_autonomous_on(monkeypatch, tmp_path):
    _setup_self_heal_env(monkeypatch, tmp_path, daily=True, autonomous=True)
    import app.brain.self_diagnose as sd
    monkeypatch.setattr(sd, "scan",
                        lambda: {"code_bugs": ["KeyError: 'missing'"], "env_issues": [],
                                 "total_error_events": 1})
    captured = {}

    def fake_auto_heal(*, report_conv_id=135):
        captured["conv"] = report_conv_id
        return {"ok": True, "action": "self_initiate", "id": "p1"}
    monkeypatch.setattr(sd, "auto_heal", fake_auto_heal)
    from app.scripts.tody_worker_loop import maybe_run_self_heal
    out = maybe_run_self_heal(dry_run=False)
    assert out["self_heal"] == "auto_heal"
    assert out["bugs_found"] == 1
    assert out["result"]["action"] == "self_initiate"
    assert captured["conv"] == 135
