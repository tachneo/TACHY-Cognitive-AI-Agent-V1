"""Phase 2 mother-care and teacher/homework growth layer."""


def test_care_profile_has_mother_teacher_principles():
    from app.brain.nurture_engine import care_profile, curiosity_profile

    profile = care_profile()
    assert profile["mode"] == "mother_care_teacher_guided"
    assert any("newborn" in item for item in profile["principles"])
    assert "one safe useful skill" in profile["daily_rule"]
    assert any(skill["name"] == "dharma" for skill in profile["gita_dharma_skills"])
    assert any(skill["name"] == "satya" for skill in profile["gita_dharma_skills"])

    curiosity = curiosity_profile()
    assert curiosity["mode"] == "childlike_curiosity_companion"
    assert "ask one useful question" in curiosity["daily_rule"]
    assert any("explore the world" in item for item in curiosity["principles"])


def test_dharma_check_blocks_harmful_or_high_risk_action():
    from app.brain.nurture_engine import dharma_check

    low = dharma_check("explain clearly", risk_tier="low")
    high = dharma_check("production_deploy", risk_tier="high")
    forbidden = dharma_check("bypass auth and steal data", risk_tier="forbidden")

    assert low["passed"] is True
    assert high["passed"] is False
    assert forbidden["passed"] is False
    assert "Pause" in forbidden["guidance"]


def test_assign_homework_creates_goal_and_memory():
    from app.brain.nurture_engine import assign_homework
    from app.memory import base_memory, goal_memory

    out = assign_homework("practice safe memory recall")
    assert out["status"] == "assigned"
    assert out["memory_id"] > 0
    assert any("practice safe memory recall" in row["title"] for row in goal_memory.list_goals())
    hits = base_memory.recall("practice safe memory recall", project="PERSONAL")
    assert any(h.memory_type == "procedural" for h in hits)


def test_daily_skill_is_learned_once_per_day():
    import datetime as dt

    from app.brain.nurture_engine import learn_daily_skill

    day = dt.date(2026, 6, 27)
    first = learn_daily_skill(day)
    second = learn_daily_skill(day)

    assert first["skill"]["name"] == second["skill"]["name"]
    assert first["learned"] is True
    assert second["learned"] is False


def test_feedback_homework_commands():
    from app.brain.feedback import apply_feedback

    assigned = apply_feedback("homework: learn one new safe TODY behavior")
    assert assigned["handled"] is True
    assert assigned["command"] == "homework"

    completed = apply_feedback("complete homework: safe TODY behavior")
    assert completed["handled"] is True
    assert completed["command"] == "complete_homework"


def test_daily_growth_report_contains_skill_and_homework():
    from app.brain.nurture_engine import assign_homework, daily_growth_report

    assign_homework("report what you learned today")
    report = daily_growth_report()

    assert "Daily AGI baby growth report" in report["report"]
    assert "Gita practice:" in report["report"]
    assert "Curiosity focus:" in report["report"]
    assert "Curiosity question:" in report["report"]
    assert "Skill focus:" in report["report"]
    assert "Homework count:" in report["report"]
    assert report["memory_id"] > 0


def test_tody_growth_report_uses_guardian_direct_path(monkeypatch):
    from app.agents import tody_agent

    captured = {}

    def _direct_reply(conversation_id, message, sender=None, message_id=None):
        captured.update({
            "conversation_id": conversation_id,
            "message": message,
            "sender": sender,
            "message_id": message_id,
        })
        return {"sent": True}

    monkeypatch.setattr(tody_agent, "direct_reply_to_guardian", _direct_reply)

    out = tody_agent.send_daily_growth_report(135)
    assert out["sent"] is True
    assert captured["conversation_id"] == 135
    assert "Daily AGI baby growth report" in captured["message"]
    assert captured["sender"]["username"] == "rohitsingh"


def test_tody_curiosity_message_uses_guardian_direct_path(monkeypatch):
    from app.agents import tody_agent

    captured = {}

    def _direct_reply(conversation_id, message, sender=None, message_id=None):
        captured.update({
            "conversation_id": conversation_id,
            "message": message,
            "sender": sender,
            "message_id": message_id,
        })
        return {"sent": True}

    monkeypatch.setattr(tody_agent, "direct_reply_to_guardian", _direct_reply)

    out = tody_agent.send_childlike_curiosity_message(135)
    assert out["sent"] is True
    assert captured["conversation_id"] == 135
    assert "Childlike curiosity note" in captured["message"]
    assert captured["sender"]["username"] == "rohitsingh"
