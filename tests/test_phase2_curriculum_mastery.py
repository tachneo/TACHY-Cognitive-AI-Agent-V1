"""CBSE/NCERT-style curriculum mastery loop."""


def test_curriculum_plan_has_12_day_mastery_gate():
    from app.brain import curriculum_learning

    plan = curriculum_learning.plan()

    assert plan["pass_mark"] == 99.0
    assert len(plan["days"]) == 12
    assert plan["days"][0]["level"] == "zero_to_class_1"
    assert plan["days"][-1]["level"] == "class_12"
    assert any("CBSE" in s["name"] for s in plan["official_sources"])
    assert any(t["name"] == "JEE/IIT" for t in plan["exam_tracks_after_class_12"])
    assert any(t["name"] == "NEET" for t in plan["exam_tracks_after_class_12"])
    assert any(t["name"] == "UPSC" for t in plan["exam_tracks_after_class_12"])


def test_study_today_stores_offline_curriculum_answers_and_promotes():
    from app.brain import curriculum_learning

    out = curriculum_learning.study_today()
    answer = curriculum_learning.answer_offline("What is subtraction?")
    status = curriculum_learning.status()

    assert out["studied"] == "zero_to_class_1"
    assert out["exam"]["score"] == 100.0
    assert out["promoted"] is True
    assert answer["known"] is True
    assert "taking away" in answer["answer"]
    assert status["current_day"] == 2
    assert "zero_to_class_1" in status["completed_levels"]


def test_curriculum_exam_requires_learned_memory():
    from app.brain import curriculum_learning

    exam = curriculum_learning.take_exam("class_10")

    assert exam["level"] == "class_10"
    assert exam["passed"] is False
    assert exam["score"] < 99.0


def test_offline_cognitive_loop_uses_curriculum_memory():
    from app.brain import curriculum_learning
    from app.brain.attention_system import Signals
    from app.brain.cognitive_loop import process

    curriculum_learning.study_today()
    out = process("What is subtraction?", Signals(), channel="chat")

    assert "taking away" in out["reply"]


def test_daily_curriculum_worker_runs_once(monkeypatch, tmp_path):
    from app.scripts import tody_worker_loop

    calls = []

    def _study_today():
        calls.append(True)
        return {"studied": "class_1", "exam": {"score": 100.0}, "promoted": True}

    monkeypatch.setenv("CURRICULUM_DAILY", "true")
    monkeypatch.setenv("CURRICULUM_DAILY_STATE_PATH", str(tmp_path / "curriculum.state"))
    monkeypatch.setattr("app.brain.curriculum_learning.study_today", _study_today)

    first = tody_worker_loop.maybe_run_daily_curriculum(dry_run=False)
    second = tody_worker_loop.maybe_run_daily_curriculum(dry_run=False)

    assert first["daily_curriculum"] == "done"
    assert first["score"] == 100.0
    assert second["daily_curriculum"] == "already_done"
    assert calls == [True]
