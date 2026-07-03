"""Phase 1S — human chat feel + clock + honest search claims (hermetic).

Driven by the 3 Jul 2026 conversation-135 audit: '[current date and time]'
placeholder replies, 'today is October 1, 2023', false 'I just checked the
latest info' claims, 'Rohit,' opening every message, assistant closers on
every message, markdown walls in a phone chat, and one-block replies.
"""
from app.agents import tody_agent
from app.brain import behavior_engine


# ── Clock ───────────────────────────────────────────────────────

def test_datetime_intent_detected():
    for msg in ("hi, what is today date and time", "what time is it now",
                "current time please", "aaj ki date kya hai"):
        st = behavior_engine.read_state(msg)
        assert st.user_intent == "datetime", msg
        assert st.reply_depth == "short"
    text = behavior_engine.style_directives(behavior_engine.read_state(
        "what is today date and time"))
    assert "clock provided in this prompt" in text


def test_prompt_contains_real_clock():
    import datetime as dt

    from app.brain.cognitive_loop import _now_line
    line = _now_line()
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30)))
    assert str(now.year) in line and now.strftime("%B") in line
    assert "IST" in line


def test_loop_injects_clock_into_prompt(monkeypatch):
    captured = {}

    class FakeProvider:
        name = "fake"

        def complete(self, system, prompt, max_tokens=800):
            captured["prompt"] = prompt
            return "ok"

    import app.brain.cognitive_loop as loop
    monkeypatch.setattr(loop, "get_provider", lambda: FakeProvider())
    loop.process("what is today date and time")
    assert "Current date & time RIGHT NOW:" in captured["prompt"]
    assert "never output a placeholder" in captured["prompt"]


# ── Honest search claims ────────────────────────────────────────

def test_no_lookup_prompt_forbids_checked_claims(monkeypatch):
    captured = {}

    class FakeProvider:
        name = "fake"

        def complete(self, system, prompt, max_tokens=800):
            captured["prompt"] = prompt
            return "ok"

    import app.brain.cognitive_loop as loop
    monkeypatch.setattr(loop, "get_provider", lambda: FakeProvider())
    loop.process("tell me about the erp fee module")
    assert "NEVER claim you checked" in captured["prompt"]


def test_new_model_questions_trigger_lookup():
    st = behavior_engine.read_state("do you know about anthropic new ai model ?")
    assert st.user_intent == "realtime_lookup"
    st = behavior_engine.read_state("latest ai model released this week")
    assert st.user_intent == "realtime_lookup"


# ── Chat-style output ───────────────────────────────────────────

def test_chat_channel_directives():
    st = behavior_engine.read_state("tell me about human behavior")
    text = behavior_engine.style_directives(st, channel="chat")
    assert "MOBILE CHAT" in text
    assert "Do NOT start messages with his name" in text
    # non-chat channels unchanged
    assert "MOBILE CHAT" not in behavior_engine.style_directives(st)


def test_strip_closers_in_chat_mode():
    draft = ("The gold rate is 14,300 per gram for 24K as of this morning. "
             "That is about 2% higher than last week.\n"
             "If you need any more information, just let me know! "
             "How else can I assist you today?")
    out = behavior_engine.humanize(draft, chat=True)
    low = out.lower()
    assert "assist you today" not in low
    assert "let me know" not in low
    assert "gold rate is 14,300" in out


def test_closers_kept_outside_chat_mode():
    draft = "Short answer here. Let me know if you need more."
    assert behavior_engine.humanize(draft) == draft


def test_plain_chat_text_flattens_markdown():
    reply = ("### Gold Update\n**Current Date and Time:**\n"
             "📅 **Friday, July 3, 2026**\n- point one\n• point two")
    out = tody_agent._plain_chat_text(reply)
    assert "**" not in out and "###" not in out
    assert "Friday, July 3, 2026" in out


def test_strip_repeated_name():
    recent = ["Rohit, I see you're feeling a bit amused.",
              "Rohit, I get it. You want me to use more features"]
    out = tody_agent._strip_repeated_name(
        "Rohit, the price went up again today.", recent)
    assert out == "The price went up again today."
    # fresh conversations keep the name
    out2 = tody_agent._strip_repeated_name(
        "Rohit, the price went up again today.", ["Something else entirely"])
    assert out2.startswith("Rohit,")


# ── Chunking (human typing rhythm) ──────────────────────────────

def test_short_reply_single_chunk():
    assert tody_agent._chat_chunks("Small reply.") == ["Small reply."]


def test_long_reply_chunks_into_bubbles():
    long = "\n\n".join(
        f"Paragraph {i} with enough words to feel like a real chat message "
        "that a person typed out to explain something." for i in range(5))
    chunks = tody_agent._chat_chunks(long)
    assert 2 <= len(chunks) <= 3
    assert all(chunks)
    joined = " ".join(chunks)
    for i in range(5):
        assert f"Paragraph {i}" in joined


def test_typing_delay_bounds():
    assert 1.5 <= tody_agent._typing_delay_seconds("short") <= 6.0
    assert tody_agent._typing_delay_seconds("x" * 2000) == 6.0


def test_guardian_multichunk_send(monkeypatch):
    long_reply = "\n\n".join(
        f"Chunk paragraph {i} with plenty of text to push the reply over the "
        "single-bubble limit so it splits into messages." for i in range(4))
    monkeypatch.setattr(tody_agent, "process", lambda *a, **k: {"reply": long_reply})
    monkeypatch.setattr(tody_agent.time, "sleep", lambda s: None)
    sent_bodies = []

    def fake_send_message(_self, conversation_id, body):
        sent_bodies.append(body)
        return {"id": f"m-{len(sent_bodies)}"}

    monkeypatch.setattr(tody_agent.get_client().__class__, "send_message",
                        fake_send_message)
    out = tody_agent.draft_reply_to_message(
        888, "explain everything", sender={"username": "rohitsingh"},
        message_id="m-chunk-1", auto_send_guardian=True)
    assert out["sent"] is True
    assert out["send_result"]["chunks"] == len(sent_bodies) >= 2
    assert "".join(sent_bodies).count("Chunk paragraph") == 4


def test_presence_honesty_in_context(monkeypatch):
    captured = {}

    def fake_process(message, signals=None, context=None, channel=None):
        captured["context"] = context
        captured["channel"] = channel
        return {"reply": "A fresh reply."}

    monkeypatch.setattr(tody_agent, "process", fake_process)
    monkeypatch.setattr(tody_agent, "request_send",
                        lambda *a, **k: {"approval": {"id": 1}})
    tody_agent.draft_reply_to_message(
        886, "why are you offline?", sender={"username": "someone"},
        message_id="m-off-1", auto_send_guardian=False)
    assert "do not show as 'online'" in captured["context"]
    assert captured["channel"] == "chat"
