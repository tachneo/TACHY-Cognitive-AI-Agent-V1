import datetime as dt


def _event(event_type, direction, conversation_id, message_id, preview, created_at, metadata="{}"):
    from app.db.models import TodyAIEventLog

    return TodyAIEventLog(
        event_type=event_type,
        status="selected" if direction == "inbound" else "sent",
        direction=direction,
        conversation_id=conversation_id,
        message_id=str(message_id),
        body_hash="h",
        body_preview=preview,
        metadata_json=metadata,
        created_at=created_at,
    )


def test_tody_ledger_finds_cross_conversation_person_history():
    from app.agents import tody_conversation_ledger as ledger
    from app.db.models import session_scope

    now = dt.datetime(2026, 7, 26, 13, 0, 0)
    with session_scope() as s:
        s.add_all([
            _event("message_selected_for_reply", "inbound", 241, 1, "Hii shree", now),
            _event("message_send_executed", "outbound", 241, 2, "Hii Niva, kaise ho?", now),
            _event("message_selected_for_reply", "inbound", 241, 3, "Good", now),
        ])

    evidence = ledger.evidence_for_person(
        "niva", exclude_conversation_id=135, now=now)
    assert evidence["conversation_ids"] == [241]
    assert evidence["event_count"] == 3
    assert evidence["inbound_count"] == 2
    assert evidence["outbound_count"] == 1


def test_verified_history_answer_corrects_today_niva_denial():
    from app.agents import tody_conversation_ledger as ledger
    from app.db.models import session_scope

    now = dt.datetime(2026, 7, 26, 13, 0, 0)
    with session_scope() as s:
        s.add_all([
            _event("message_selected_for_reply", "inbound", 241, 1, "How are you", now),
            _event("message_send_executed", "outbound", 241, 2, "Hii Niva, I am good.", now),
        ])

    answer = ledger.verified_history_answer(
        "tumne aaj niva se baat bhi ki?", current_conversation_id=135, now=now)
    assert answer is not None
    assert "haan" in answer.lower()
    assert "records" in answer.lower()
    assert "conversation 241" in answer.lower()
    assert "galti" in answer.lower()


def test_verified_history_answer_respects_ever_scope_no_aaj_template():
    from app.agents import tody_conversation_ledger as ledger

    now = dt.datetime(2026, 7, 26, 13, 0, 0)
    answer = ledger.verified_history_answer(
        "aaj nahi, kya kabhi bhi tumne @khalid se baat ki?",
        current_conversation_id=135,
        now=now,
    )

    assert answer is not None
    assert "kabhi bhi khalid" in answer.lower()
    assert "aaj khalid" not in answer.lower()


def test_verified_history_answer_respects_kal_parso_scope():
    from app.agents import tody_conversation_ledger as ledger
    from app.db.models import session_scope

    now = dt.datetime(2026, 7, 26, 13, 0, 0)
    yesterday_utc = dt.datetime(2026, 7, 25, 8, 0, 0)
    with session_scope() as s:
        s.add_all([
            _event("message_selected_for_reply", "inbound", 333, 1, "Hello Shree", yesterday_utc, '{"sender_username":"khalid"}'),
            _event("message_send_executed", "outbound", 333, 2, "Hi Khalid", yesterday_utc),
        ])

    answer = ledger.verified_history_answer(
        "kal ya parso tumne baat kiya tha @khalid se?",
        current_conversation_id=135,
        now=now,
    )

    assert answer is not None
    assert "kal ya parso khalid" in answer.lower()
    assert "conversation 333" in answer.lower()
    assert "aaj khalid" not in answer.lower()


def test_conflicting_history_denial_is_rewritten():
    from app.agents import tody_conversation_ledger as ledger
    from app.db.models import session_scope

    now = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    with session_scope() as s:
        s.add(_event(
            "message_send_executed", "outbound", 241, 7,
            "Niva, main tumhara schedule bana sakti hoon.", now))

    rewritten = ledger.rewrite_conflicting_history_claim(
        "Nahi Papa, Niva se koi baat nahi hui.",
        "fir jhoot? check karo, niva ne bataya ki usne tumse baat ki",
        current_conversation_id=135,
    )
    assert "haan" in rewritten.lower()
    assert "niva" in rewritten.lower()
    assert "koi baat nahi hui" not in rewritten.lower()


def test_tody_agent_uses_verified_history_before_llm(monkeypatch):
    from app.agents import tody_agent
    from app.db.models import session_scope

    now = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    with session_scope() as s:
        s.add_all([
            _event("message_selected_for_reply", "inbound", 241, 11, "Hii shree", now),
            _event("message_send_executed", "outbound", 241, 12, "Hii Niva!", now),
        ])

    def fail_process(*_args, **_kwargs):
        raise AssertionError("LLM should not be called for verified history")

    monkeypatch.setattr(tody_agent, "process", fail_process)
    monkeypatch.setattr(tody_agent, "request_send", lambda *a, **k: {"approval": {"id": 1}})

    out = tody_agent.draft_reply_to_message(
        135,
        "tumne aaj niva se baat bhi ki?",
        sender={"username": "rohitsingh", "email": "rohitji.patna@gmail.com"},
        message_id="truth-niva-1",
        auto_send_guardian=False,
    )
    assert out["queued"]["approval"]["id"] == 1
    assert "records" in out["draft"].lower()
    assert "niva" in out["draft"].lower()
    assert "galti" in out["draft"].lower()
