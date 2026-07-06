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


def test_worker_loop_defaults_are_rate_limit_safe(monkeypatch):
    from app.scripts import tody_worker_loop

    assert tody_worker_loop.DEFAULT_WORKER_INTERVAL >= 90
    assert 2 <= tody_worker_loop.DEFAULT_FAST_REPLY_INTERVAL <= 5
    assert tody_worker_loop.DEFAULT_ERROR_BACKOFF >= 1800
    assert tody_worker_loop.DEFAULT_RATE_LIMIT_BACKOFF >= 3600


def test_fast_reply_conversation_id_prefers_explicit_env(monkeypatch):
    from app.scripts import tody_worker_loop

    monkeypatch.setenv("TODY_FAST_REPLY_CONVERSATION_ID", "135")
    monkeypatch.setenv("TODY_DAILY_CURIOSITY_CONVERSATION_ID", "999")

    assert tody_worker_loop._fast_reply_conversation_id() == 135


def test_fast_reply_conversation_id_can_fallback_to_daily_chat(monkeypatch):
    from app.scripts import tody_worker_loop

    monkeypatch.delenv("TODY_FAST_REPLY_CONVERSATION_ID", raising=False)
    monkeypatch.setenv("TODY_DAILY_CURIOSITY_CONVERSATION_ID", "135")

    assert tody_worker_loop._fast_reply_conversation_id() == 135


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


def test_presence_heartbeat_skips_dry_run(monkeypatch):
    from app.scripts import tody_worker_loop

    monkeypatch.setenv("TODY_PRESENCE_HEARTBEAT_ENABLED", "true")

    out = tody_worker_loop.maybe_update_presence(dry_run=True)

    assert out == {"presence_heartbeat": "disabled"}


def test_presence_heartbeat_updates_online_status(monkeypatch):
    from app.scripts import tody_worker_loop

    class FakeClient:
        def presence_heartbeat(self):
            return {"presence": [{"uuid": "u1"}], "typing": [{"conversation_id": 135}]}

    monkeypatch.setenv("TODY_PRESENCE_HEARTBEAT_ENABLED", "true")
    monkeypatch.setattr(tody_worker_loop, "get_client", lambda: FakeClient())

    out = tody_worker_loop.maybe_update_presence(dry_run=False)

    assert out == {
        "presence_heartbeat": "ok",
        "presence_count": 1,
        "typing_count": 1,
    }


def test_presence_heartbeat_failure_does_not_raise(monkeypatch):
    from app.scripts import tody_worker_loop

    class BrokenClient:
        def presence_heartbeat(self):
            raise RuntimeError("poll failed")

    monkeypatch.setenv("TODY_PRESENCE_HEARTBEAT_ENABLED", "true")
    monkeypatch.setattr(tody_worker_loop, "get_client", lambda: BrokenClient())

    out = tody_worker_loop.maybe_update_presence(dry_run=False)

    assert out["presence_heartbeat"] == "failed"
    assert out["error"] == "RuntimeError"


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
