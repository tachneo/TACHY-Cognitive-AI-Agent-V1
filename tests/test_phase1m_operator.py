"""Phase 1M — runtime operator loop safeguards."""
import importlib


def test_worker_loop_refuses_live_without_confirm(monkeypatch):
    from app.scripts import tody_worker_loop

    monkeypatch.delenv("TODY_WORKER_LIVE_CONFIRM", raising=False)
    monkeypatch.setattr("sys.argv", ["tody_worker_loop", "--live"])

    assert tody_worker_loop.main() == 2


def test_worker_loop_importable():
    mod = importlib.import_module("app.scripts.tody_worker_loop")
    assert callable(mod.main)


def test_systemd_templates_exist():
    from pathlib import Path

    root = Path("deploy/systemd")
    assert (root / "tachy-brain.service").exists()
    assert (root / "tachy-tody-worker.service").exists()


def test_daily_growth_report_skips_dry_run(monkeypatch, tmp_path):
    from app.scripts import tody_worker_loop

    monkeypatch.setenv("TODY_DAILY_GROWTH_REPORT", "true")
    monkeypatch.setenv("TODY_DAILY_GROWTH_CONVERSATION_ID", "135")
    monkeypatch.setenv("TODY_DAILY_GROWTH_STATE_PATH", str(tmp_path / "daily.state"))

    out = tody_worker_loop.maybe_send_daily_growth_report(dry_run=True)

    assert out == {"daily_growth_report": "disabled"}


def test_daily_growth_report_sends_once_per_day(monkeypatch, tmp_path):
    from app.scripts import tody_worker_loop

    calls = []

    def _send(conversation_id):
        calls.append(conversation_id)
        return {"sent": True}

    monkeypatch.setenv("TODY_DAILY_GROWTH_REPORT", "true")
    monkeypatch.setenv("TODY_DAILY_GROWTH_CONVERSATION_ID", "135")
    monkeypatch.setenv("TODY_DAILY_GROWTH_STATE_PATH", str(tmp_path / "daily.state"))
    monkeypatch.setattr(tody_worker_loop.tody_agent, "send_daily_growth_report", _send)

    first = tody_worker_loop.maybe_send_daily_growth_report(dry_run=False)
    second = tody_worker_loop.maybe_send_daily_growth_report(dry_run=False)

    assert first["daily_growth_report"] == "sent"
    assert second["daily_growth_report"] == "already_sent"
    assert calls == [135]


def test_daily_curiosity_message_sends_once_per_day(monkeypatch, tmp_path):
    from app.scripts import tody_worker_loop

    calls = []

    def _send(conversation_id):
        calls.append(conversation_id)
        return {"sent": True}

    monkeypatch.setenv("TODY_DAILY_CURIOSITY_MESSAGE", "true")
    monkeypatch.setenv("TODY_DAILY_CURIOSITY_CONVERSATION_ID", "135")
    monkeypatch.setenv("TODY_DAILY_CURIOSITY_STATE_PATH", str(tmp_path / "curiosity.state"))
    monkeypatch.setattr(tody_worker_loop.tody_agent, "send_childlike_curiosity_message", _send)

    first = tody_worker_loop.maybe_send_daily_curiosity_message(dry_run=False)
    second = tody_worker_loop.maybe_send_daily_curiosity_message(dry_run=False)

    assert first["daily_curiosity_message"] == "sent"
    assert second["daily_curiosity_message"] == "already_sent"
    assert calls == [135]
