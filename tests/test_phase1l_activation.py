"""Phase 1L — live TODY activation checklist and manual command."""


def test_preflight_reports_missing_credentials_without_network(monkeypatch):
    from app.agents import tody_activation, tody_agent
    from app.config import get_settings

    monkeypatch.setenv("INTERNAL_API_KEY", "key")
    monkeypatch.setenv("TODY_EMAIL", "")
    monkeypatch.setenv("TODY_PASSWORD", "")
    get_settings.cache_clear()

    def _connect():
        raise AssertionError("default preflight must not call TODY")

    monkeypatch.setattr(tody_agent, "connect", _connect)

    out = tody_activation.preflight(check_login=False)
    assert out["login"]["checked"] is False
    assert out["checks"]["internal_api_key_configured"] is True
    assert out["checks"]["tody_email_configured"] is False
    assert out["ready_for_manual_processing"] is False
    assert out["ready_for_background_worker"] is False


def test_preflight_can_check_login_when_requested(monkeypatch):
    from app.agents import tody_activation, tody_agent
    from app.config import get_settings

    monkeypatch.setenv("INTERNAL_API_KEY", "key")
    monkeypatch.setenv("TODY_EMAIL", "bot@example.com")
    monkeypatch.setenv("TODY_PASSWORD", "secret")
    get_settings.cache_clear()

    monkeypatch.setattr(
        tody_agent,
        "connect",
        lambda: {"connected": True, "as": {"username": "brain"}},
    )

    out = tody_activation.preflight(check_login=True)
    assert out["login"]["checked"] is True
    assert out["checks"]["tody_login_ok"] is True
    assert out["ready_for_manual_processing"] is True


def test_process_one_delegates_to_worker(monkeypatch):
    from app.agents import tody_activation, tody_worker

    captured = {}

    def _poll_once(*, dry_run=True, conversation_limit=10, message_limit=10):
        captured.update({
            "dry_run": dry_run,
            "conversation_limit": conversation_limit,
            "message_limit": message_limit,
        })
        return {"processed": False, "dry_run": dry_run, "reason": "test"}

    monkeypatch.setattr(tody_worker, "poll_once", _poll_once)

    out = tody_activation.process_one(
        dry_run=True, conversation_limit=3, message_limit=4
    )
    assert captured == {"dry_run": True, "conversation_limit": 3, "message_limit": 4}
    assert out["manual_activation"] is True
    assert out["note"] == "Dry run only; no draft or send performed."


def test_worker_doc_contains_disabled_service_warning():
    from pathlib import Path

    text = Path("TODY_WORKER.md").read_text()
    assert "Do not install or enable this until Rohit approves." in text
    assert "refuses live" in text
    assert "TODY_WORKER_LIVE_CONFIRM=YES" in text
