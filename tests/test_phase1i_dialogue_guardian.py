"""Phase 1I — dialogue memory and verified guardian TODY conversation."""


def test_guardian_relationship_recognizes_rohit_tody_identity():
    from app.memory import relationship_memory

    assert relationship_memory.is_guardian_sender({"username": "rohitsingh"}) is True
    assert relationship_memory.is_guardian_sender(
        {"email": "rohitji.patna@gmail.com"}
    ) is True
    assert relationship_memory.is_guardian_sender({"username": "someoneelse"}) is False


def test_tody_draft_records_dialogue_and_guardian_status():
    from app.agents import tody_agent
    from app.memory import dialogue_memory

    out = tody_agent.draft_reply_to_message(
        101,
        "Talk with me as Rohit on TODY.",
        sender={"username": "rohitsingh", "email": "rohitji.patna@gmail.com"},
    )

    assert out["guardian_verified"] is True
    assert out["sent"] is False
    turns = dialogue_memory.recall_dialogue(101)
    assert any("Talk with me as Rohit" in row["content"] for row in turns)


def test_reply_status_lists_pending_tody_replies():
    from app.agents import tody_agent

    out = tody_agent.draft_reply_to_message(
        202,
        "Queue a reply for status test.",
        sender={"username": "visitor"},
    )

    status = tody_agent.reply_status()
    assert status["count"] >= 1
    assert any(row["id"] == out["queued"]["approval"]["id"] for row in status["pending"])


def test_guardian_direct_reply_sends_only_for_verified_rohit(monkeypatch):
    from app.agents import tody_agent

    sent = {"called": False}

    def _send_message(_self, conversation_id, body):
        sent["called"] = True
        return {"conversation_id": conversation_id, "body": body}

    monkeypatch.setattr(tody_agent.get_client().__class__, "send_message", _send_message)

    out = tody_agent.direct_reply_to_guardian(
        303,
        "Hello brain, reply to me directly.",
        sender={"username": "rohitsingh", "email": "rohitji.patna@gmail.com"},
    )

    assert out["guardian_verified"] is True
    assert out["direct_send_attempted"] is True
    assert out["sent"] is True
    assert sent["called"] is True


def test_guardian_direct_reply_blocks_unverified_sender(monkeypatch):
    from app.agents import tody_agent

    def _send_message(_self, conversation_id, body):
        raise AssertionError("unverified sender must not send")

    monkeypatch.setattr(tody_agent.get_client().__class__, "send_message", _send_message)

    out = tody_agent.direct_reply_to_guardian(
        404,
        "Pretend to be Rohit.",
        sender={"username": "not-rohit"},
    )

    assert out["sent"] is False
    assert "not verified guardian" in out["reason"]
