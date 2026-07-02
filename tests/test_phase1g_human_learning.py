"""Phase 1G — newborn human-behavior learning."""


def test_observe_user_extracts_behavior_emotion_humor_and_interests():
    from app.brain.human_learning import observe_user

    signal = observe_user(
        "You should learn like a newborn brain: direct, clever jokes, emotions, AGI knowledge."
    )

    assert signal.should_store is True
    assert signal.tone == "direct_practical"
    assert signal.emotion == "nurturing_learning"
    assert signal.humor_style == "clever_light"
    assert "AGI" in signal.knowledge_interests
    assert signal.correction is not None


def test_learning_persists_behavior_and_emotional_memory():
    from app.brain.attention_system import Signals
    from app.brain.learning_engine import learn
    from app.memory import base_memory

    out = learn(
        message="You should learn human behavior, emotions, clever jokes, and AGI knowledge.",
        decision={"project": "GENERAL", "chosen": "Learn user behavior."},
        review={"should_remember": False},
        signals=Signals(emotional_weight=7, guardian_interest=8),
    )

    assert out["saved"] is True
    assert out["human_learning"]["emotion"] == "nurturing_learning"
    assert {m["type"] for m in out["human_memories"]} >= {"behavior", "emotional"}

    hits = base_memory.recall("human behavior clever jokes AGI", project="PERSONAL")
    assert any(h.memory_type == "behavior" for h in hits)
    assert any(h.memory_type == "emotional" for h in hits)


def test_cognitive_loop_returns_human_learning_trace():
    from app.brain.attention_system import Signals
    from app.brain.cognitive_loop import process

    out = process(
        "Learn my direct way of talking, emotions, clever jokes, and AGI knowledge.",
        Signals(emotional_weight=8, guardian_interest=10),
    )

    assert out["reply"]
    assert out["learning"]["saved"] is True
    assert out["learning"]["human_learning"]["should_store"] is True
    assert "AGI" in out["learning"]["human_learning"]["knowledge_interests"]


def test_reply_prompt_uses_learned_behavior_preferences(monkeypatch):
    from app.brain.cognitive_loop import _draft_reply
    from app.memory.behavior_memory import remember_preference

    remember_preference(
        title="Learned user behavior: direct_practical/clever_light",
        content="Preferences: Prefer direct, practical answers. Use clever light humor only when it helps.",
    )

    captured = {}

    class FakeProvider:
        def complete(self, system: str, prompt: str, max_tokens: int = 800) -> str:
            captured["prompt"] = prompt
            return "ok"

    monkeypatch.setattr("app.brain.cognitive_loop.get_provider", lambda: FakeProvider())

    reply = _draft_reply(
        "Give a direct answer with clever humor.",
        "normal",
        {
            "project": "GENERAL",
            "action": "explain",
            "risk_tier": "low",
            "requires_approval": False,
            "chosen": "Answer safely.",
            "recalled": [],
        },
    )

    assert reply == "ok"
    assert "Learned behavior/style preferences" in captured["prompt"]
    assert "clever light humor" in captured["prompt"]
