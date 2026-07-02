"""Phase 0.1 — HTTP auth, validation, audit, and approval binding."""


def _fresh_app(monkeypatch, api_key: str = "test-key", env: str = "production"):
    monkeypatch.setenv("APP_ENV", env)
    monkeypatch.setenv("INTERNAL_API_KEY", api_key)
    from app.config import get_settings
    get_settings.cache_clear()
    return get_settings()


def test_internal_api_key_accepts_only_configured_secret(monkeypatch):
    import pytest
    from fastapi import HTTPException

    _fresh_app(monkeypatch)

    from app.safety.auth import require_internal_api_key

    require_internal_api_key("test-key")
    with pytest.raises(HTTPException) as exc:
        require_internal_api_key("wrong")
    assert exc.value.status_code == 401


def test_production_fails_closed_without_api_key(monkeypatch):
    import pytest
    from fastapi import HTTPException

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("INTERNAL_API_KEY", "")
    from app.config import get_settings
    get_settings.cache_clear()

    from app.safety.auth import require_internal_api_key

    with pytest.raises(HTTPException) as exc:
        require_internal_api_key(None)
    assert exc.value.status_code == 503


def test_development_without_api_key_allows_local_work(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("INTERNAL_API_KEY", "")
    from app.config import get_settings
    get_settings.cache_clear()

    from app.safety.auth import require_internal_api_key

    assert require_internal_api_key(None) is None


def test_app_routes_except_health_are_auth_protected():
    from fastapi.routing import APIRoute

    from app.main import app
    from app.safety.auth import require_internal_api_key

    exposed = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path == "/health":
            continue
        calls = {dep.call for dep in route.dependant.dependencies}
        if require_internal_api_key not in calls:
            exposed.append(route.path)

    assert exposed == []


def test_route_validation_rejects_out_of_range_scores():
    import pytest
    from pydantic import ValidationError

    from app.api.routes_chat import ChatRequest

    with pytest.raises(ValidationError):
        ChatRequest(message="hello", security_risk=99)


def test_approval_writes_audit_log():
    from sqlalchemy import select

    from app.db.models import CognitiveAuditLog, session_scope
    from app.safety import approvals

    req = approvals.request_approval("production_deploy", payload="fees module")
    approvals.respond(req["id"], approved=True)

    with session_scope() as s:
        actions = [
            row.action
            for row in s.scalars(
                select(CognitiveAuditLog).order_by(CognitiveAuditLog.id)
            ).all()
        ]

    assert "approval_requested" in actions
    assert "approval_decided" in actions


def test_tody_approval_payload_mismatch_is_blocked(monkeypatch):
    from app.agents import tody_agent
    from app.safety import approvals

    sent = {"called": False}

    def _send_message(_self, conversation_id, body):
        sent["called"] = True
        return {"conversation_id": conversation_id, "body": body}

    monkeypatch.setattr(tody_agent.get_client().__class__, "send_message", _send_message)

    q = tody_agent.request_send(123, "approved body")
    aid = q["approval"]["id"]
    approvals.respond(aid, approved=True)

    blocked = tody_agent.execute_send(aid, 123, "changed body")
    assert blocked["sent"] is False
    assert "payload mismatch" in blocked["reason"]
    assert sent["called"] is False


def test_tody_approval_matching_payload_can_execute(monkeypatch):
    from app.agents import tody_agent
    from app.safety import approvals

    def _send_message(_self, conversation_id, body):
        return {"conversation_id": conversation_id, "body": body}

    monkeypatch.setattr(tody_agent.get_client().__class__, "send_message", _send_message)

    q = tody_agent.request_send(123, "approved body")
    aid = q["approval"]["id"]
    approvals.respond(aid, approved=True)

    sent = tody_agent.execute_send(aid, 123, "approved body")
    assert sent["sent"] is True
    assert sent["result"]["body"] == "approved body"
