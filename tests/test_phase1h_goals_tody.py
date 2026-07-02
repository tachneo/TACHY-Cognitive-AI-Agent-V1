"""Phase 1H — goals, personality, feedback, and safe TODY conversation."""


def test_goal_memory_create_and_list():
    from app.memory import goal_memory

    goal = goal_memory.create_goal(
        title="Build safe AGI newborn brain", horizon="long", project="GENERAL"
    )
    assert goal["id"] > 0
    assert goal["memory_id"] > 0

    goals = goal_memory.list_goals(project="GENERAL")
    assert any(row["id"] == goal["id"] for row in goals)


def test_personality_synthesizes_from_behavior_memory():
    from app.brain.personality import synthesize_profile
    from app.memory.behavior_memory import remember_preference

    remember_preference(
        title="Explicit behavior correction",
        content="Correction: Prefer direct practical answers with clever light humor about AGI.",
    )

    profile = synthesize_profile()
    assert profile["memory_count"] >= 1
    assert "direct_practical" in profile["traits"]
    assert "light_clever_humor_when_useful" in profile["traits"]
    assert "agi" in profile["knowledge_interests"]


def test_feedback_commands_shape_memory_and_goals():
    from app.brain.feedback import apply_feedback
    from app.memory import base_memory, goal_memory

    remembered = apply_feedback("remember this: TODY brain account is for safe conversation.")
    assert remembered["handled"] is True
    assert remembered["command"] == "remember"

    corrected = apply_feedback("correct your behavior: be precise and never harm production.")
    assert corrected["command"] == "correct_behavior"

    goal = apply_feedback("set goal: learn Rohit's working style safely")
    assert goal["command"] == "set_goal"

    hits = base_memory.recall("safe conversation", project="PERSONAL")
    assert any(h.memory_type == "belief" for h in hits)
    assert goal_memory.list_goals()


def test_tody_draft_reply_queues_approval_without_sending(monkeypatch):
    from app.agents import tody_agent

    called = {"send": False}

    def _send_message(_self, conversation_id, body):
        called["send"] = True
        return {"conversation_id": conversation_id, "body": body}

    monkeypatch.setattr(tody_agent.get_client().__class__, "send_message", _send_message)

    out = tody_agent.draft_reply_to_message(
        conversation_id=55,
        message="Hello brain, learn my direct TODY talking style.",
    )

    assert out["sent"] is False
    assert out["queued"]["queued"] is True
    assert out["queued"]["approval"]["risk_tier"] == "high"
    assert called["send"] is False


def test_tody_process_latest_reads_message_and_queues_reply(monkeypatch):
    from app.agents import tody_agent

    def _messages(_self, conversation_id, limit=30):
        return {"messages": [{"id": 1, "body": "Can you talk with me on TODY?"}]}

    def _send_message(_self, conversation_id, body):
        raise AssertionError("drafting latest reply must not send")

    monkeypatch.setattr(tody_agent.get_client().__class__, "messages", _messages)
    monkeypatch.setattr(tody_agent.get_client().__class__, "send_message", _send_message)

    out = tody_agent.process_latest_message(77)
    assert out["processed"] is True
    assert out["sent"] is False
    assert out["source_message"]["body"] == "Can you talk with me on TODY?"
    assert out["queued"]["approval"]["status"] == "pending"
