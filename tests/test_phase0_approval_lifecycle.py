"""Approval authorizations are atomic and single-use across execution paths."""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor


def test_action_approval_cannot_be_replayed(monkeypatch):
    from app.brain import action_engine, inner_life
    from app.safety import approvals

    calls = 0

    def _consolidate():
        nonlocal calls
        calls += 1
        return {"archived": 0}

    monkeypatch.setattr(inner_life, "consolidate", _consolidate)
    proposal = action_engine.propose("consolidate_memory", {})
    approval_id = proposal["approval"]["id"]
    approvals.respond(approval_id, approved=True)

    first = action_engine.execute_approved(approval_id)
    second = action_engine.execute_approved(approval_id)

    assert first["executed"] is True
    assert first["approval_status"] == "succeeded"
    assert second == {"executed": False, "reason": "approval is succeeded"}
    assert calls == 1


def test_concurrent_action_execution_has_one_winner(monkeypatch):
    from app.brain import action_engine, inner_life
    from app.safety import approvals

    calls = 0
    calls_lock = threading.Lock()
    start = threading.Barrier(2)

    def _consolidate():
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return {"archived": 0}

    monkeypatch.setattr(inner_life, "consolidate", _consolidate)
    proposal = action_engine.propose("consolidate_memory", {})
    approval_id = proposal["approval"]["id"]
    approvals.respond(approval_id, approved=True)

    def _execute():
        start.wait()
        return action_engine.execute_approved(approval_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: _execute(), range(2)))

    assert sum(bool(result.get("executed")) for result in results) == 1
    assert calls == 1
    assert approvals.get_approval(approval_id)["status"] == "succeeded"


def test_send_approval_cannot_be_replayed(monkeypatch):
    from app.agents import tody_agent
    from app.safety import approvals

    calls = 0

    def _send_message(_self, conversation_id, body):
        nonlocal calls
        calls += 1
        return {"id": 801, "conversation_id": conversation_id, "body": body}

    monkeypatch.setattr(tody_agent.get_client().__class__, "send_message", _send_message)
    queued = tody_agent.request_send(123, "single use")
    approval_id = queued["approval"]["id"]
    approvals.respond(approval_id, approved=True)

    first = tody_agent.execute_send(approval_id, 123, "single use")
    second = tody_agent.execute_send(approval_id, 123, "single use")

    assert first["sent"] is True
    assert first["approval_status"] == "succeeded"
    assert second == {"sent": False, "reason": "approval not approved"}
    assert calls == 1


def test_concurrent_send_execution_has_one_winner(monkeypatch):
    from app.agents import tody_agent
    from app.safety import approvals

    calls = 0
    calls_lock = threading.Lock()
    start = threading.Barrier(2)

    def _send_message(_self, conversation_id, body):
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return {"id": 802, "conversation_id": conversation_id, "body": body}

    monkeypatch.setattr(tody_agent.get_client().__class__, "send_message", _send_message)
    queued = tody_agent.request_send(456, "concurrent")
    approval_id = queued["approval"]["id"]
    approvals.respond(approval_id, approved=True)

    def _execute():
        start.wait()
        return tody_agent.execute_send(approval_id, 456, "concurrent")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: _execute(), range(2)))

    assert sum(bool(result.get("sent")) for result in results) == 1
    assert calls == 1
    assert approvals.get_approval(approval_id)["status"] == "succeeded"


def test_multichunk_send_supersedes_whole_reply_approval(monkeypatch):
    from app.agents import tody_agent
    from app.safety import approvals

    monkeypatch.setattr(
        tody_agent.relationship_memory, "is_guardian_sender", lambda _sender: True,
    )
    monkeypatch.setattr(
        tody_agent, "process", lambda *args, **kwargs: {"reply": "whole reply"},
    )
    monkeypatch.setattr(tody_agent, "_chat_chunks", lambda _reply: ["part 1", "part 2"])
    monkeypatch.setattr(tody_agent.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        tody_agent.get_client().__class__,
        "send_message",
        lambda _self, conversation_id, body: {
            "id": f"sent-{body}", "conversation_id": conversation_id, "body": body,
        },
    )

    result = tody_agent.draft_reply_to_message(
        777,
        "explain",
        sender={"uuid": "guardian"},
        message_id="multi-chunk-lifecycle",
        auto_send_guardian=True,
    )

    original_id = result["queued"]["approval"]["id"]
    assert result["sent"] is True
    assert approvals.get_approval(original_id)["status"] == "superseded"
    succeeded = approvals.list_by_action("send_message", status="succeeded")
    assert len(succeeded) == 2


def test_failed_send_is_terminal_and_cannot_retry(monkeypatch):
    from app.agents import tody_agent
    from app.integrations.tody_client import TodyError
    from app.safety import approvals

    calls = 0

    def _fail(_self, _conversation_id, _body):
        nonlocal calls
        calls += 1
        raise TodyError("simulated send failure")

    monkeypatch.setattr(tody_agent.get_client().__class__, "send_message", _fail)
    queued = tody_agent.request_send(991, "will fail")
    approval_id = queued["approval"]["id"]
    approvals.respond(approval_id, approved=True)

    first = tody_agent.execute_send(approval_id, 991, "will fail")
    second = tody_agent.execute_send(approval_id, 991, "will fail")

    assert first["sent"] is False
    assert first["approval_status"] == "failed"
    assert second == {"sent": False, "reason": "approval not approved"}
    assert calls == 1
