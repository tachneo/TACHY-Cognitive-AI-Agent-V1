"""Phase 1W — capability honesty (hermetic).

Driven by the live conv-135 failure: Rohit asked the brain to message @TACHY /
@zarathakoo; the brain repeatedly claimed "I'll send it right away" / "I'll
resend it" though it has no tool to message other users — pure hallucinated
action, an honesty-rule violation.
"""
from app.agents import tody_agent
from app.brain import behavior_engine


# ── Intent detection ────────────────────────────────────────────

def test_third_party_action_intent():
    for msg in ("can you do same message to @TACHY as well",
                "send message to @zarathakoo",
                "tell @rohit I will be late",
                "please contact @someone about the meeting",
                "send the same message to TACHY too"):
        st = behavior_engine.read_state(msg)
        assert st.user_intent == "third_party_action", msg


def test_normal_messages_not_flagged():
    for msg in ("what is the gold price today", "explain the fee module",
                "how are you"):
        assert behavior_engine.read_state(msg).user_intent != "third_party_action"


def test_third_party_directives_are_honest():
    st = behavior_engine.read_state("send message to @TACHY")
    text = behavior_engine.style_directives(st)
    assert "cannot do that yet" in text or "cannot" in text.lower()


# ── False-send detector ─────────────────────────────────────────

def test_claims_false_send_catches_hallucinations():
    for reply in (
        "I'll send the message to @TACHY right away.",
        "Sure, I'll send the same message to @TACHY as well.",
        "Got it, I'll resend the message to @TACHY right now.",
        "The message has been sent.",
        "I've notified them about the meeting.",
        "I'll make sure they get it this time.",
        "It goes out right away.",
    ):
        assert behavior_engine.claims_false_send(reply), reply


def test_claims_false_send_ignores_honest_replies():
    for reply in (
        "I can't send messages to other users yet. Want me to draft it?",
        "The gold price today is 14,300 per gram.",
        "Here is the message text you can send: 'Hi, can we talk tomorrow?'",
        "I understand the meeting is tomorrow.",
    ):
        assert not behavior_engine.claims_false_send(reply), reply


# ── Prompt grounding ────────────────────────────────────────────

def test_capability_block_injected(monkeypatch):
    captured = {}

    class FakeProvider:
        name = "fake"

        def complete(self, system, prompt, max_tokens=800):
            captured["prompt"] = prompt
            return "ok"

    import app.brain.cognitive_loop as loop
    monkeypatch.setattr(loop, "get_provider", lambda: FakeProvider())
    loop.process("send message to @TACHY", channel="chat")
    prompt = captured["prompt"]
    assert "send message to @username" in prompt
    assert "would be a\n        \"lie" in prompt or "be a lie" in prompt.replace("\n", " ").replace("  ", " ") or "lie" in prompt
    assert "NOT sent anything yourself" in prompt


# ── End-to-end backstop in the TODY path ────────────────────────

def test_false_send_reply_is_rewritten(monkeypatch):
    monkeypatch.setattr(
        tody_agent, "process",
        lambda *a, **k: {"reply": "Sure Rohit, I'll send the same message to "
                         "@TACHY right away.",
                         "behavior": {"state": {"user_intent": "third_party_action"}}})
    monkeypatch.setattr(tody_agent, "request_send",
                        lambda *a, **k: {"approval": {"id": 1}})
    out = tody_agent.draft_reply_to_message(
        135, "send same message to @TACHY", sender={"username": "rohitsingh"},
        message_id="tp-1", auto_send_guardian=False)
    draft = out["draft"].lower()
    assert "send message to @username" in draft
    assert not behavior_engine.claims_false_send(out["draft"])


def test_honest_reply_passes_through(monkeypatch):
    honest = "The fee module handles invoices and receipts. Want details?"
    monkeypatch.setattr(
        tody_agent, "process",
        lambda *a, **k: {"reply": honest,
                         "behavior": {"state": {"user_intent": "question"}}})
    monkeypatch.setattr(tody_agent, "request_send",
                        lambda *a, **k: {"approval": {"id": 1}})
    out = tody_agent.draft_reply_to_message(
        135, "explain the fee module", sender={"username": "rohitsingh"},
        message_id="tp-2", auto_send_guardian=False)
    assert out["draft"] == honest
