"""Phase 2E — local offline brain talks without external LLM."""

from app.brain.cognitive_loop import process


def test_offline_brain_answers_own_brain_without_llm():
    result = process("do you have your own brain without LLM?", channel="chat")
    low = result["reply"].lower()

    assert "local brain" in low
    assert "without llm" in low or "without model" in low
    assert "api key" not in low
    assert "offline at the moment" not in low


def test_offline_brain_answers_agi_stage_honestly():
    result = process("what stage and percentage of AGI are you currently?", channel="chat")
    low = result["reply"].lower()

    assert "not agi yet" in low or "not full agi" in low
    assert "0%" in result["reply"]
    assert "architecture" in low


def test_offline_brain_explains_social_body_without_fake_action():
    result = process("can you search TODY user and send message, create post and like post?", channel="chat")
    low = result["reply"].lower()

    assert "social body" in low
    assert "search users" in low
    assert "create posts" in low
    assert "approval" in low
    assert "message sent" not in low


def test_broken_llm_falls_back_to_local_brain(monkeypatch):
    class BrokenLLM:
        name = "nvidia"

        def complete(self, system, prompt, max_tokens=800):
            raise RuntimeError("provider down")

    import app.brain.cognitive_loop as loop

    monkeypatch.setattr(loop, "get_provider", lambda: BrokenLLM())

    result = loop.process("without LLM can you still talk to me?", channel="chat")
    low = result["reply"].lower()

    assert "local brain" in low
    assert "provider down" not in low
    assert "api key" not in low

