"""Phase 1J — conversation sessions, replay safety, and identity continuity."""


def test_dialogue_replay_marker_blocks_duplicate_message():
    from app.memory import dialogue_memory

    assert dialogue_memory.was_processed("tody", 501, "m1") is False
    dialogue_memory.mark_processed("tody", 501, "m1")
    assert dialogue_memory.was_processed("tody", 501, "m1") is True


def test_tody_draft_reply_rejects_duplicate_message_id():
    from app.agents import tody_agent

    first = tody_agent.draft_reply_to_message(
        502,
        "First message for replay test.",
        sender={"username": "rohitsingh"},
        message_id="abc-1",
    )
    second = tody_agent.draft_reply_to_message(
        502,
        "First message for replay test.",
        sender={"username": "rohitsingh"},
        message_id="abc-1",
    )

    assert first["processed"] is True
    assert second["processed"] is False
    assert second["duplicate"] is True


def test_process_latest_message_uses_source_message_id(monkeypatch):
    from app.agents import tody_agent

    def _messages(_self, conversation_id, limit=30):
        return {
            "messages": [
                {
                    "id": "latest-1",
                    "body": "Continue our TODY conversation.",
                    "sender": {"username": "rohitsingh"},
                }
            ]
        }

    monkeypatch.setattr(tody_agent.get_client().__class__, "messages", _messages)

    first = tody_agent.process_latest_message(503)
    second = tody_agent.process_latest_message(503)

    assert first["processed"] is True
    assert first["source_message"]["id"] == "latest-1"
    assert second["processed"] is False
    assert second["duplicate"] is True


def test_conversation_status_contains_summary_after_turns():
    from app.agents import tody_agent

    tody_agent.draft_reply_to_message(
        504,
        "Remember this TODY session context.",
        sender={"username": "rohitsingh"},
        message_id="status-1",
    )

    status = tody_agent.conversation_status(504)
    assert status["conversation_id"] == 504
    assert status["session"]["turn_count"] >= 2
    assert "TODY" in status["session"]["summary"] or status["dialogue"]
    assert status["auto_reply_enabled"] is False


def test_identity_context_is_passed_to_brain_prompt(monkeypatch):
    from app.agents import tody_agent

    captured = {}

    class FakeProvider:
        def complete(self, system: str, prompt: str, max_tokens: int = 800) -> str:
            captured["prompt"] = prompt
            return "identity reply"

    monkeypatch.setattr("app.brain.cognitive_loop.get_provider", lambda: FakeProvider())

    out = tody_agent.draft_reply_to_message(
        505,
        "Who are you talking to?",
        sender={"username": "rohitsingh"},
        message_id="identity-1",
    )

    assert out["draft"] == "identity reply"
    assert "continuing a TODY conversation with Rohit Kumar" in captured["prompt"]


def test_guardian_direct_reply_duplicate_does_not_resend(monkeypatch):
    from app.agents import tody_agent

    sent = {"count": 0}

    def _send_message(_self, conversation_id, body):
        sent["count"] += 1
        return {"conversation_id": conversation_id, "body": body}

    monkeypatch.setattr(tody_agent.get_client().__class__, "send_message", _send_message)

    first = tody_agent.direct_reply_to_guardian(
        506,
        "Direct reply once.",
        sender={"username": "rohitsingh"},
        message_id="direct-1",
    )
    second = tody_agent.direct_reply_to_guardian(
        506,
        "Direct reply once.",
        sender={"username": "rohitsingh"},
        message_id="direct-1",
    )

    assert first["sent"] is True
    assert second["processed"] is False
    assert second["duplicate"] is True
    assert sent["count"] == 1


def test_execute_send_marks_sent_message_processed(monkeypatch):
    from app.agents import tody_agent
    from app.memory import dialogue_memory
    from app.safety import approvals

    def _send_message(_self, conversation_id, body):
        return {"message": {"id": "out-1"}}

    monkeypatch.setattr(tody_agent.get_client().__class__, "send_message", _send_message)

    q = tody_agent.request_send(507, "outbound body")
    approvals.respond(q["approval"]["id"], approved=True)
    sent = tody_agent.execute_send(q["approval"]["id"], 507, "outbound body")

    assert sent["sent"] is True
    assert dialogue_memory.was_processed("tody", 507, "out-1") is True
