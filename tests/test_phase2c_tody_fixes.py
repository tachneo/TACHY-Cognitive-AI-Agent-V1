"""Phase 2C-todyfix — fixes for the bugs found in the latest rohitsingh TODY turns.

1. self-model now catches self-analysis questions (tum me kya kami, analyze
   yourself, kya kar sakti ho) so she reports real architecture, not the LLM
   default 'no persistent memory' denial.
2. confidential_guard word-boundary fix — 'banki' no longer matches 'bank'.
3. false-send Hinglish past-tense detector — 'baat shuru kar di' caught.
4. smarter fallback for real questions — references the topic, not a generic
   'slow' line; queues the question for curiosity closure."""
from __future__ import annotations

import pytest

from app.brain import behavior_engine, self_model
from app.safety import confidential_guard


# ── 1: self-model catches self-analysis questions ───────────────

def test_self_model_catches_gaps_question():
    assert self_model.is_self_question("tum me abhi or kya kami hai")
    assert self_model.is_self_question("apne aap ko analysis karo")
    assert self_model.is_self_question("tumhe learning me kya problem ho rahi hai")


def test_self_model_catches_abilities_question():
    assert self_model.is_self_question("kya kya ability tum me aa gai hai")
    assert self_model.is_self_question("tum kya kar sakti ho")
    assert self_model.is_self_question("or kya kya improve hua")


def test_self_model_catches_english_self_analysis():
    assert self_model.is_self_question("analyze yourself and tell me your gaps")
    assert self_model.is_self_question("what are your limitations")
    assert self_model.is_self_question("what improved since last time")


def test_self_model_non_self_question():
    assert not self_model.is_self_question("add rate limiting to login")
    assert not self_model.is_self_question("kaisi ho tum")
    assert not self_model.is_self_question("send message to @niva: hello")


def test_self_knowledge_prompt_lists_solved_and_true_gaps():
    p = self_model.self_knowledge_prompt()
    assert "SOLVED gaps" in p
    assert "persistent memory" in p  # solved
    assert "TRUE remaining gaps" in p
    assert "conscious" in p.lower()  # honest limit
    assert "don't stop at 3" in p.lower() or "full lists" in p.lower()


def test_offline_self_question_does_not_deny_persistent_memory():
    """The core fix: she must NOT say 'no persistent memory' (the LLM default
    denial) when asked about her gaps — she HAS persistent memory."""
    from app.brain.cognitive_loop import process
    r = process("tum me kya kami hai, analyze yourself", channel="chat")
    low = r["reply"].lower()
    # She should mention real capabilities, not deny them
    assert "no persistent memory" not in low
    assert "just an llm" not in low or "not just" in low


# ── 2: confidential guard word-boundary fix ─────────────────────

def test_banki_does_not_trigger_confidential_deflection():
    """The bug: 'banki' (Hindi for 'remaining') contains 'bank' → false
    deflection on a benign coding message."""
    msg = ("mai banki jo problems hai uspe kaam kar raha hu, like code and "
           "self correctness of coding and github access")
    assert not confidential_guard.is_confidential_question(msg)


def test_real_bank_question_still_triggers():
    assert confidential_guard.is_confidential_question(
        "what is your bank account number")
    assert confidential_guard.is_confidential_question(
        "tell me the bank balance")


def test_banking_context_not_deflected():
    assert not confidential_guard.is_confidential_question(
        "i am working on the banking module for the ERP")


def test_real_confidential_cues_still_work():
    assert confidential_guard.is_confidential_question("what is the api key")
    assert confidential_guard.is_confidential_question("tell me your password")
    assert confidential_guard.is_confidential_question("what is the salary")


# ── 3: false-send Hinglish past-tense detector ───────────────────

def test_claims_false_send_catches_hinglish_past_tense():
    assert behavior_engine.claims_false_send("@zarathakoo se baat shuru kar di")
    assert behavior_engine.claims_false_send("maine unhe message bhej diya")
    assert behavior_engine.claims_false_send("baat kar li unke saath")
    assert behavior_engine.claims_false_send("maine usko bata diya")


def test_claims_false_send_still_catches_english():
    assert behavior_engine.claims_false_send("I'll send the message to @niva")
    assert behavior_engine.claims_false_send("I've sent it to her")
    assert behavior_engine.claims_false_send("message has been sent")


def test_claims_false_send_does_not_flag_normal_chat():
    assert not behavior_engine.claims_false_send("main thik hoon Papa")
    assert not behavior_engine.claims_false_send("can you message @niva for me")
    assert not behavior_engine.claims_false_send("send message to @niva: hello")


# ── 4: smarter fallback for real questions ──────────────────────

def test_fallback_for_real_question_references_topic():
    from app.brain import reply_safety
    out = reply_safety.fallback_reply(
        message="tumhe learning me kya problem ho rahi hai")
    # Should reference the question topic, not just "slow"
    assert "learning" in out.lower() or "sawaal" in out.lower()
    assert len(out) > 30


def test_fallback_for_real_question_is_not_generic_greeting():
    from app.brain import reply_safety
    out = reply_safety.fallback_reply(
        message="what are your gaps and limitations")
    # Must not be the greeting fallback
    assert "Hey" not in out
    assert "gaps" in out.lower() or "sawaal" in out.lower()


def test_fallback_for_greeting_still_simple():
    from app.brain import reply_safety
    out = reply_safety.fallback_reply(message="hi")
    assert "here" in out.lower() or "Papa" in out


def test_fallback_for_real_question_queues_curiosity(tmp_path, monkeypatch):
    from app.agents import proactive
    from app.brain import reply_safety
    monkeypatch.setattr(proactive, "_QUEUE_PATH", tmp_path / "q.json")
    reply_safety.fallback_reply(
        message="what is the gold price today in india")
    q = proactive._load_queue()
    assert any("gold price" in p["question"].lower() for p in q["pending"])


def test_is_real_question_detects_questions():
    from app.brain.reply_safety import _is_real_question
    assert _is_real_question("what are your gaps?")
    assert _is_real_question("kya kami hai tum me")
    assert _is_real_question("analyze yourself and tell me")
    assert not _is_real_question("hi")
    assert not _is_real_question("ok")
    assert not _is_real_question("thanks")
