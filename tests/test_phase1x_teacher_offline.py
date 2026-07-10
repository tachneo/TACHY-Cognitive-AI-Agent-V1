"""Phase 1X — teacher-student learning + smart offline talking (hermetic)."""
import pytest

from app.brain import teacher_learning
from app.brain.attention_system import Signals


@pytest.fixture(autouse=True)
def fresh_settings():
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ── Teacher store ───────────────────────────────────────────────

def test_remember_and_recall_exchange():
    teacher_learning.remember_exchange(
        message="what is our refund policy for the ERP?",
        reply="We offer a 14-day pro-rata refund on annual ERP plans, minus setup.")
    hit = teacher_learning.recall_reply("tell me the erp refund policy")
    assert hit and "14-day pro-rata" in hit["reply"]
    assert hit["score"] >= 0.5


def test_recall_returns_none_when_dissimilar():
    teacher_learning.remember_exchange(
        message="how do I add a student to a class?",
        reply="Open Students → Add, pick the class, save.")
    assert teacher_learning.recall_reply("what is the gold price today") is None


def test_short_or_empty_replies_not_stored():
    assert teacher_learning.remember_exchange(message="hi", reply="ok") is None
    assert teacher_learning.remember_exchange(message="", reply="x" * 50) is None
    assert teacher_learning.remember_exchange(
        message="q", reply="[reply fallback — LLM provider error: X]") is None


def test_duplicate_question_not_restored():
    first = teacher_learning.remember_exchange(
        message="how do teachers mark attendance?",
        reply="They use the attendance tab on the class dashboard, then submit.")
    dup = teacher_learning.remember_exchange(
        message="how do teachers mark attendance",  # near-identical
        reply="Different phrasing of the same answer here for the class.")
    assert first and dup is None


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("TEACHER_LEARNING_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    assert teacher_learning.remember_exchange(
        message="anything at all here", reply="a" * 40) is None


# ── Teacher learns from a real LLM in the loop ──────────────────

def test_loop_caches_llm_reply(monkeypatch):
    class FakeLLM:
        name = "fake"

        def complete(self, system, prompt, max_tokens=800):
            return "Design it as a separate behavior engine with memory and gates."

    import app.brain.cognitive_loop as loop
    monkeypatch.setattr(loop, "get_provider", lambda: FakeLLM())
    loop.process("how should I structure the AGI conversation layer?")
    hit = teacher_learning.recall_reply("structure the agi conversation layer")
    assert hit and "behavior engine" in hit["reply"]


def test_loop_does_not_cache_realtime(monkeypatch):
    class FakeLLM:
        name = "fake"

        def complete(self, system, prompt, max_tokens=800):
            return "The gold price today is 14,300 per gram."

    import app.brain.cognitive_loop as loop
    monkeypatch.setattr(loop, "get_provider", lambda: FakeLLM())
    monkeypatch.setattr(loop, "_live_web_lookup",
                        lambda m, max_pages=2: {"fetched": False, "sources": []})
    loop.process("what is the gold price today", channel="chat")
    assert teacher_learning.recall_reply("gold price today") is None


# ── Offline talking (no LLM = heuristic provider) ───────────────

def test_offline_reuses_learned_answer(monkeypatch):
    teacher_learning.remember_exchange(
        message="how do I raise a fee invoice?",
        reply="Go to Fees → New Invoice, pick the student and fee head, save.")
    # Default provider is heuristic (no key) under the test env → offline path.
    from app.brain.cognitive_loop import process
    result = process("how do I raise a fee invoice for a student?", channel="chat")
    assert "New Invoice" in result["reply"]


def test_offline_answers_datetime_from_clock():
    from app.brain.cognitive_loop import process
    result = process("what is today date and time", channel="chat")
    assert "IST" in result["reply"]
    assert "offline" not in result["reply"].lower()


def test_offline_realtime_is_honest(monkeypatch):
    import app.brain.cognitive_loop as loop
    monkeypatch.setattr(loop, "_live_web_lookup",
                        lambda m, max_pages=2: {"fetched": False, "sources": []})
    result = loop.process("check gold price online right now", channel="chat")
    low = result["reply"].lower()
    assert "offline" in low or "can't" in low
    assert "14," not in result["reply"]  # never fabricates a number


def test_offline_greeting_is_natural():
    from app.brain.cognitive_loop import process
    result = process("hi", channel="chat")
    assert "offline" not in result["reply"].lower()
    assert "api key" not in result["reply"].lower()


def test_offline_never_leaks_prompt_or_begs_for_key():
    from app.brain.cognitive_loop import process
    result = process("tell me something about quantum entanglement", channel="chat")
    low = result["reply"].lower()
    assert "user message" not in low
    assert "api key" not in low
    assert "current date & time right now" not in low


# ── Heuristic provider itself is clean ──────────────────────────

def test_heuristic_provider_no_leak_no_key_beg():
    from app.llm.provider import HeuristicProvider
    prompt = ("Current date & time RIGHT NOW: Friday...\n\n"
              "User message (normal attention): explain webhooks\n\n"
              "Project: TODY | ...")
    out = HeuristicProvider().complete("sys", prompt)
    low = out.lower()
    assert "user message" not in low
    assert "api key" not in low
    assert "current date & time" not in low


def test_extract_user_message_gets_last_occurrence():
    from app.llm.provider import _extract_user_message
    prompt = ("Current date & time RIGHT NOW: today\n\n"
              "User message (normal attention): the real question here\n\n"
              "Project: X")
    assert _extract_user_message(prompt) == "the real question here"


def test_learned_route_mounted():
    from app.main import app
    from app.api.routes_behavior import learned

    assert "get" in app.openapi()["paths"]["/behavior/learned"]
    assert "learned_replies" in learned()
