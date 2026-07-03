"""Phase 1R — TODY conversation quality fixes (hermetic).

Driven by real conversation-135 failures: repeated greetings, stale-topic
rehashing, template leakage, unkept "I'll check the internet" promises, and
LLM error traces sent to the user.
"""
from app.agents import tody_agent
from app.brain import behavior_engine


# ── New intents ─────────────────────────────────────────────────

def test_greeting_intent_short_friend():
    for msg in ("hi", "Hello!", "how are you", "good morning", "kaise ho"):
        st = behavior_engine.read_state(msg)
        assert st.user_intent == "greeting", msg
        assert st.reply_depth == "short"
        assert st.relationship_mode == "friend"
    text = behavior_engine.style_directives(behavior_engine.read_state("hi"))
    assert "just a greeting" in text.lower()


def test_realtime_lookup_intent():
    for msg in ("can you tell me price about gold in india today",
                "check on internet and let me know actual gold price today",
                "latest news about AI"):
        st = behavior_engine.read_state(msg)
        assert st.user_intent == "realtime_lookup", msg
        assert st.next_action == "realtime_lookup"
        assert st.reply_depth == "short"


def test_self_emotion_intent_uses_mood():
    st = behavior_engine.read_state("do you feel happy or sad ever?")
    assert st.user_intent == "self_emotion"
    text = behavior_engine.style_directives(st, mood_label="positive/calm")
    assert "positive/calm" in text
    assert "emotion engine" in text
    assert "canned line" in text


def test_directives_forbid_repetition_and_future_promises():
    text = behavior_engine.style_directives(
        behavior_engine.read_state("tell me about the erp"))
    low = text.lower()
    assert "newest message" in low
    assert "never reuse their openings" in low
    assert "the real issue is" in low  # forbidden-phrase instruction present
    assert "check/fetch/look something up later" in low


# ── Live web lookup wiring ──────────────────────────────────────

def test_live_lookup_runs_for_realtime_intent(monkeypatch):
    calls = {}

    def fake_lookup(message, max_pages=2):
        calls["query"] = message
        return {"query": message, "fetched": True, "sources": [
            {"title": "Gold Rate", "url": "https://example.com/gold",
             "text": "24k gold price today is X per 10g"}]}

    import app.brain.cognitive_loop as loop
    monkeypatch.setattr(loop, "_live_web_lookup", fake_lookup)
    result = loop.process("tell me gold price in india today")
    assert calls, "live lookup was not triggered"
    assert result["live_web"]["fetched"] is True


def test_live_lookup_skipped_for_normal_messages(monkeypatch):
    import app.brain.cognitive_loop as loop

    def boom(message, max_pages=2):
        raise AssertionError("lookup must not run")

    monkeypatch.setattr(loop, "_live_web_lookup", boom)
    result = loop.process("explain the fee module design")
    assert result["live_web"] is None


# ── Fallback guard + opening dedup ──────────────────────────────

def test_llm_error_reply_is_never_sent(monkeypatch):
    monkeypatch.setattr(
        tody_agent, "process",
        lambda *a, **k: {"reply": "[reply fallback — LLM provider error: X]\nPlan: y"})
    sent = []
    monkeypatch.setattr(tody_agent, "request_send",
                        lambda *a, **k: sent.append(a) or {"approval": {"id": 1}})
    out = tody_agent.draft_reply_to_message(
        999, "hello", sender={"username": "rohitsingh"}, message_id="m-err-1")
    assert out["processed"] is False
    assert out["llm_error"] is True
    assert sent == []
    # not marked processed → retried next tick
    from app.memory import dialogue_memory
    assert dialogue_memory.was_processed("tody", 999, "m-err-1") is False


def test_dedupe_opening_strips_repeated_greeting():
    recent = ["Hi Rohit, it's good to see you. I understand that you"]
    reply = ("Hi Rohit, it's good to see you. The gold price today is 72,400 "
             "per 10g as per live data.")
    out = tody_agent._dedupe_opening(reply, recent)
    assert not out.startswith("Hi Rohit")
    assert "gold price today" in out.lower()


def test_dedupe_opening_keeps_fresh_replies():
    reply = "Bhai, aaj ka gold price 72,400 hai per 10 gram."
    assert tody_agent._dedupe_opening(reply, ["Hi Rohit, it's good"]) == reply


def test_recent_openings_collected_and_injected(monkeypatch):
    from app.memory import dialogue_memory
    for i in range(2):
        dialogue_memory.remember_turn(
            channel="tody", conversation_id=777, direction="inbound",
            body=f"question {i}", message_id=f"in-{i}")
        dialogue_memory.remember_turn(
            channel="tody", conversation_id=777, direction="draft_outbound",
            body="Hi Rohit, it's good to see you. Something else here.")
    openings = tody_agent._recent_reply_openings(777)
    assert openings and openings[0].startswith("Hi Rohit")

    captured = {}

    def fake_process(message, signals=None, context=None, channel=None):
        captured["context"] = context
        return {"reply": "Fresh reply about the topic, no repeat."}

    monkeypatch.setattr(tody_agent, "process", fake_process)
    monkeypatch.setattr(tody_agent, "request_send",
                        lambda *a, **k: {"approval": {"id": 1}})
    tody_agent.draft_reply_to_message(
        777, "next question", sender={"username": "someone"},
        message_id="in-99", auto_send_guardian=False)
    assert "do NOT start like any of these" in captured["context"]
    assert "Hi Rohit" in captured["context"]


def test_dialogue_context_labels_roles():
    from app.memory import dialogue_memory
    dialogue_memory.remember_turn(channel="tody", conversation_id=555,
                                  direction="inbound", body="hello there")
    dialogue_memory.remember_turn(channel="tody", conversation_id=555,
                                  direction="draft_outbound", body="hi, how can I help")
    ctx = dialogue_memory.identity_context(555, person="Rohit Kumar")
    assert "User: hello there" in ctx
    assert "You: hi, how can I help" in ctx
    assert "reply only to the newest User message" in ctx
