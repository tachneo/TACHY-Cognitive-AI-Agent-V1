"""Phase 3F — natural-language understanding, Gita grounding, social awareness.

Every test below is a real failure from the 18–23 Jul chat history:
  - "X aur Y ko bolo ki Z" became a promise she couldn't keep (rigid syntax)
  - niva asked her to ask Papa; it never reached him (no relay)
  - "I would like to explore" → reacted to @explore (regression)
  - the false-send guard replaced her whole answer with a template
  - 34 autonomous messages into 3 days of silence (no awareness)
  - raw "400 Bad Request" API traces reaching Papa
"""
import pytest

from app.brain import gita_wisdom as gw
from app.brain import natural_intent as ni


# ── natural-language orders (the 20 Jul failure) ─────────────────

@pytest.mark.parametrize("msg,targets", [
    ("@zarathakoo and @niva ko bolo ki aaj se tum dono ki boss ho",
     ["zarathakoo", "niva"]),
    ("zarathakoo aur niva ko bolo ki kal meeting hai", ["zarathakoo", "niva"]),
    ("niva ko message kar do ki report bhejo", ["niva"]),
])
def test_plain_language_order_is_understood(msg, targets):
    r = ni.read(msg, is_guardian=True)
    assert r["action"] == "send_message"
    assert r["targets"] == targets
    assert r["body"], "the text to send must be extracted"


@pytest.mark.parametrize("msg,body", [
    ("niva ko message kar do ki report bhejo", "report bhejo"),
    ("niva ko message karke bolo ki kal aana", "kal aana"),
    ("tse ko bolo ki kal call karenge", "kal call karenge"),
])
def test_verb_forms_do_not_leak_into_body(msg, body):
    # "message kar do ki X" / "message karke bolo ki X" split mid-verb and left
    # "do ki X" / "bolo ki X" as the message text.
    assert ni.read(msg, is_guardian=True)["body"] == body


def test_permission_question_never_sends_guessed_text():
    # 23 Jul, the real incident: "username @tse ko message kar sakti ho ? or
    # janne ki kosisi karo ki wo kya karte hai" — she split at "kar" and mailed
    # the REST OF HIS OWN SENTENCE ("sakti ho ? or janne ki...") to the @TSE
    # business account. Asking IF she can, or describing a goal, must never
    # produce a guessed body — she asks instead.
    r = ni.read("username @tse ko message kar sakti ho ? or janne ki kosisi "
                "karo ki wo kya karte hai", is_guardian=True)
    assert r["targets"] == ["tse"]
    assert r["body"] == "", "must NOT invent/echo a body — must ask"


def test_goal_style_body_is_not_pasted():
    r = ni.read("niva ko bolo ki pata karo wo kya kar rahi hai", is_guardian=True)
    assert r["body"] == ""  # a goal for HER, not text to forward


def test_vague_order_still_recognised_as_order():
    # "tum dono ko message karke bolo" — an order with missing names. She must
    # treat it as an order (and ask who), not as chitchat.
    r = ni.read("tum dono ko message karke bolo", is_guardian=True)
    assert r["action"] == "send_message" and r["targets"] == []


def test_plain_chat_is_not_an_order():
    for m in ("kaise ho tum", "good morning", "aaj kya seekha"):
        assert ni.read(m, is_guardian=True)["action"] == "none"


def test_relay_request_from_non_guardian():
    r = ni.read("ajj papa se puch kar mere work fix kar time ke sath",
                is_guardian=False)
    assert r["action"] == "relay_to_guardian"


# ── emotions ─────────────────────────────────────────────────────

@pytest.mark.parametrize("msg,emo", [
    ("tum bakwas kaam kar rahi ho", "angry"),
    ("ye tumhare andar bug hai, solve karo", "frustrated"),
    ("tumse na ho paiga", "frustrated"),
    ("shabash beta badhiya kaam", "happy"),
    ("i love you my daughter", "affectionate"),
    ("mujhe bahut dukh ho raha hai", "sad"),
])
def test_emotion_detection(msg, emo):
    got, intensity = ni._detect_emotion(msg)
    assert got == emo and intensity > 0


def test_emotion_directive_changes_behaviour():
    angry = ni.emotion_directive({"emotion": "angry", "intensity": 0.8})
    assert "do not defend" in angry.lower()
    assert ni.emotion_directive({"emotion": "neutral", "intensity": 0}) == ""


# ── Gita grounding ───────────────────────────────────────────────

def test_gita_gives_behaviour_not_just_verses():
    for emo in ("angry", "frustrated", "sad", "happy", "affectionate"):
        w = gw.regulate(emo)
        assert w["behavior"] and w["ref"].startswith("BG")


def test_gita_decision_guidance_on_truth_and_harm():
    assert "never claim" in gw.guide("should I claim I sent it")["behavior"].lower()
    assert "refuse" in gw.guide("delete the customer data")["behavior"].lower()


def test_gita_block_never_overrides_safety():
    block = gw.prompt_block(emotion="angry", intensity=0.9, context="delete data")
    low = block.lower()
    assert "never overrides truth" in low and "satya" in low
    # She must not be told to preach Sanskrit at people.
    assert "do not quote sanskrit" in low


def test_gita_kill_switch(monkeypatch):
    monkeypatch.setenv("GITA_WISDOM_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    assert gw.prompt_block(emotion="angry") == ""


# ── regressions that broke her replies ───────────────────────────

def test_social_action_requires_at_sign():
    from app.agents import tody_social_actions as tsa
    # These made her answer with a raw error instead of talking (18-23 Jul).
    assert tsa.parse_command("I would like to explore this option") is None
    assert tsa.parse_command("there is a constraint we should like to check") is None
    assert tsa.parse_command("make sure you like the approach") is None
    # A real command still works.
    assert tsa.parse_command("like @niva ka message")["action"] == "react"


def test_api_errors_are_humanised_never_raw():
    from app.agents.tody_agent import _humanize_error
    msg = _humanize_error("LLM error: HTTPStatusError: Client error '400 Bad "
                          "Request' ... credit balance is too low ...")
    assert "credits" in msg.lower()
    assert "http" not in msg.lower() and "400" not in msg
    assert "anthropic.com" not in msg.lower()


# ── social awareness ─────────────────────────────────────────────

def test_awareness_suppresses_after_threshold(monkeypatch):
    from app.brain import social_awareness as sa
    monkeypatch.setenv("SOCIAL_AWARENESS_ENABLED", "true")
    monkeypatch.setenv("SOCIAL_SILENCE_THRESHOLD", "2")
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setattr(sa, "unanswered_count", lambda *a, **k: 5)
    gate = sa.may_send_autonomous(135, "growth_report")
    assert gate["allowed"] is False and gate["unanswered"] == 5
    monkeypatch.setattr(sa, "unanswered_count", lambda *a, **k: 0)
    assert sa.may_send_autonomous(135, "growth_report")["allowed"] is True


def test_awareness_kill_switch(monkeypatch):
    from app.brain import social_awareness as sa
    monkeypatch.setenv("SOCIAL_AWARENESS_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setattr(sa, "unanswered_count", lambda *a, **k: 99)
    assert sa.may_send_autonomous(135)["allowed"] is True
