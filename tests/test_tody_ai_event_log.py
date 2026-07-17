import json


def test_tody_event_log_hashes_and_redacts_body():
    from app.agents import tody_event_log
    from app.db.models import TodyAIEventLog, session_scope

    row_id = tody_event_log.record_event(
        "message_observed",
        conversation_id=135,
        message_id="m1",
        direction="inbound",
        actor="test",
        body="email me at rohit@example.com token=nvapi-secret-value phone +91 9876543210",
        metadata={"url": "https://example.test/private?token=secret", "note": "ok"},
    )
    assert row_id is not None

    with session_scope() as s:
        row = s.get(TodyAIEventLog, row_id)
        assert row is not None
        assert row.body_hash
        assert "rohit@example.com" not in row.body_preview
        assert "nvapi-secret-value" not in row.body_preview
        assert "9876543210" not in row.body_preview
        metadata = json.loads(row.metadata_json)
        assert metadata["url"] == "[REDACTED]"
        assert metadata["note"] == "ok"


def test_tody_attachment_state_updates_and_retries():
    from app.agents import tody_event_log
    from app.db.models import TodyAttachmentState, session_scope

    attachment = {"id": "img-1", "mime_type": "image/jpeg", "size_bytes": 1234}
    first_id = tody_event_log.record_attachment_observed(135, "m2", attachment)
    second_id = tody_event_log.record_attachment_result(
        135, "m2", attachment, status="pending_retry", error="Bearer secret failed")

    assert first_id == second_id
    with session_scope() as s:
        row = s.get(TodyAttachmentState, first_id)
        assert row is not None
        assert row.status == "pending_retry"
        assert row.retry_count == 1
        assert row.next_retry_at is not None
        assert "secret" not in (row.last_error or "").lower()


def test_worker_records_inbound_message_and_attachment(monkeypatch):
    from app.agents import tody_agent, tody_worker
    from app.db.models import TodyAIEventLog, TodyAttachmentState, session_scope

    row = {
        "id": "m3",
        "body": "please check this image",
        "sender": {"username": "rohitsingh", "name": "Rohit Kumar"},
        "attachment": {"id": "img-2", "mime_type": "image/png"},
    }
    monkeypatch.setattr(tody_agent, "_message_items", lambda data: data["messages"])
    monkeypatch.setattr(tody_agent, "_message_body", lambda item: item["body"])
    monkeypatch.setattr(tody_agent, "_message_attachment", lambda item: item["attachment"])
    monkeypatch.setattr(tody_agent, "_message_sender", lambda item: item["sender"])

    candidate = tody_worker._latest_unprocessed_message(135, {"messages": [row]})
    assert candidate["message_id"] == "m3"
    assert candidate["attachments"][0]["source_message_id"] == "m3"

    with session_scope() as s:
        events = s.query(TodyAIEventLog).all()
        attachments = s.query(TodyAttachmentState).all()
        assert any(event.event_type == "message_observed" for event in events)
        assert len(attachments) == 1
        assert attachments[0].attachment_id == "img-2"


def test_execute_send_records_outbound_event(monkeypatch):
    from app.agents import tody_agent
    from app.db.models import TodyAIEventLog, session_scope
    from app.safety import approvals

    class FakeClient:
        def send_message(self, conversation_id, body, reply_to_message_id=None):
            return {"id": "sent-1", "conversation_id": conversation_id, "body": body}

    monkeypatch.setattr(tody_agent, "get_client", lambda: FakeClient())
    queued = tody_agent.request_send(135, "outbound body")
    approval_id = queued["approval"]["id"]
    approvals.respond(approval_id, approved=True)

    result = tody_agent.execute_send(approval_id, 135, "outbound body")
    assert result["sent"] is True

    with session_scope() as s:
        events = s.query(TodyAIEventLog).filter_by(event_type="message_send_executed").all()
        assert len(events) == 1
        assert events[0].message_id == "sent-1"
        assert events[0].body_hash
        assert events[0].body_preview == "outbound body"
