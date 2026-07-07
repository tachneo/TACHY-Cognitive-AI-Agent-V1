"""Phase 1K — dry-run TODY worker and status."""


def test_worker_dry_run_reports_candidate_without_processing(monkeypatch):
    from app.agents import tody_agent, tody_worker

    def _inbox(limit=10):
        return {"conversations": [{"id": 601}]}

    def _messages(conversation_id, limit=10):
        return {"messages": [{"id": "w1", "body": "Hello from TODY worker dry run."}]}

    def _process_latest_message(conversation_id, limit=10):
        raise AssertionError("dry run must not process or draft")

    monkeypatch.setattr(tody_agent, "inbox", _inbox)
    monkeypatch.setattr(tody_agent, "messages", _messages)
    monkeypatch.setattr(tody_agent, "process_latest_message", _process_latest_message)

    out = tody_worker.poll_once(dry_run=True)
    assert out["processed"] is False
    assert out["dry_run"] is True
    assert out["candidate"]["conversation_id"] == 601
    assert out["candidate"]["message_id"] == "w1"


def test_worker_processes_one_message_when_not_dry_run(monkeypatch):
    from app.agents import tody_agent, tody_worker

    def _inbox(limit=10):
        return {"conversations": [{"conversation_id": 602}]}

    def _messages(conversation_id, limit=10):
        return {"messages": [{"message_id": "w2", "body": "Process this once."}]}

    def _draft_reply_to_message(conversation_id, body, *, sender=None,
                                message_id=None, extra_message_ids=None, auto_send_guardian=None):
        return {"processed": True, "conversation_id": conversation_id,
                "message_id": message_id, "body": body}

    def _process_latest_message(conversation_id, limit=10):
        raise AssertionError("worker must process selected candidate directly")

    monkeypatch.setattr(tody_agent, "inbox", _inbox)
    monkeypatch.setattr(tody_agent, "messages", _messages)
    monkeypatch.setattr(tody_agent, "draft_reply_to_message", _draft_reply_to_message)
    monkeypatch.setattr(tody_agent, "process_latest_message", _process_latest_message)

    out = tody_worker.poll_once(dry_run=False)
    assert out["processed"] is True
    assert out["conversation_id"] == 602
    assert out["message_id"] == "w2"
    assert out["dry_run"] is False


def test_worker_status_records_last_result(monkeypatch):
    from app.agents import tody_agent, tody_worker

    def _inbox(limit=10):
        return {"conversations": []}

    monkeypatch.setattr(tody_agent, "inbox", _inbox)

    out = tody_worker.poll_once(dry_run=True)
    status = tody_worker.status()

    assert out["processed"] is False
    assert status["runs"] >= 1
    assert status["last_result"]["reason"] == "no conversations found"
    assert status["locked"] is False


def test_worker_skips_already_processed_candidate(monkeypatch):
    from app.agents import tody_agent, tody_worker
    from app.memory import dialogue_memory

    dialogue_memory.mark_processed("tody", 604, "w4")

    def _inbox(limit=10):
        return {"conversations": [{"id": 604}]}

    def _messages(conversation_id, limit=10):
        return {"messages": [{"id": "w4", "body": "Already handled."}]}

    monkeypatch.setattr(tody_agent, "inbox", _inbox)
    monkeypatch.setattr(tody_agent, "messages", _messages)

    out = tody_worker.poll_once(dry_run=True)
    assert out["processed"] is False
    assert out["reason"] == "no unprocessed text messages found"


def test_fast_conversation_poll_uses_messages_without_inbox(monkeypatch):
    from app.agents import tody_agent, tody_worker

    def _inbox(limit=10):
        raise AssertionError("fast conversation poll must not scan inbox")

    def _messages(conversation_id, limit=10):
        assert conversation_id == 135
        return {"messages": [{"id": "fast-1", "body": "Reply quickly."}]}

    def _draft_reply_to_message(conversation_id, body, *, sender=None,
                                message_id=None, extra_message_ids=None,
                                auto_send_guardian=None):
        return {
            "processed": True,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "body": body,
        }

    monkeypatch.setattr(tody_agent, "inbox", _inbox)
    monkeypatch.setattr(tody_agent, "messages", _messages)
    monkeypatch.setattr(tody_agent, "draft_reply_to_message", _draft_reply_to_message)

    out = tody_worker.poll_conversation_once(135, dry_run=False)

    assert out["processed"] is True
    assert out["fast_conversation"] is True
    assert out["conversation_id"] == 135
    assert out["message_id"] == "fast-1"
