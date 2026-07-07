"""Phase 2C-agi — stronger brain: never-silent, no prompt leakage, true
self-model, action continuity, memory dedup + rich recall, proactive people
recall, world model, and the self-review reflection loop."""
from __future__ import annotations

import pytest

from app.brain import reply_safety, self_model, world_model
from app.brain.attention_system import Signals


# ── 1: never-silent reply guarantee ──────────────────────────────

def test_finalize_reply_uses_fallback_for_empty():
    out = reply_safety.finalize_reply("", message="hi", emotion=None)
    assert out and len(out) > 10
    assert "Papa" in out or "here" in out.lower()


def test_finalize_reply_uses_fallback_for_whitespace():
    out = reply_safety.finalize_reply("   \n  ", message="kaisi ho")
    assert out.strip() and len(out) > 10


def test_finalize_reply_passes_through_meaningful():
    out = reply_safety.finalize_reply("Main thik hoon Papa, aap batao.",
                                       message="kaisi ho")
    assert out == "Main thik hoon Papa, aap batao."


def test_fallback_reply_is_never_empty_for_any_message():
    for msg in ["", "hi", "kaisi ho tum", "xyz random", "did niva reply?"]:
        out = reply_safety.fallback_reply(message=msg)
        assert out.strip() and len(out) > 8


def test_fallback_reply_includes_real_emotion():
    emo = {"top_emotions": [{"name": "Joy", "intensity": 0.6}]}
    out = reply_safety.fallback_reply(message="hi", emotion=emo)
    assert "happy" in out.lower() or "feeling" in out.lower()


# ── 2: prompt-leak sanitizer ─────────────────────────────────────

def test_sanitize_strips_i_understood_leak():
    raw = ("I understood: Current date & time RIGHT NOW: Saturday, 04 July 2026 "
           "5:45 PM IST (Asia/Kolkata). never us. I will answer directly.")
    out = reply_safety.sanitize_reply(raw)
    assert "I understood" not in out
    assert "Current date" not in out


def test_sanitize_strips_decision_trace():
    raw = "Project: GENERAL | Action: explain | Risk: low Relevant memory:\n- x"
    out = reply_safety.sanitize_reply(raw)
    assert "Project:" not in out and "Relevant memory" not in out


def test_finalize_replaces_leak_only_reply_with_fallback():
    raw = "I understood: Current date & time RIGHT NOW: Saturday. never us."
    out = reply_safety.finalize_reply(raw, message="good morning")
    # The leak is stripped → not meaningful → warm fallback replaces it
    assert "I understood" not in out
    assert "Current date" not in out
    assert len(out) > 10


def test_meaningful_detects_emoji_only_as_meaningful():
    assert reply_safety.is_meaningful("💛")
    assert not reply_safety.is_meaningful("...")
    assert not reply_safety.is_meaningful("")
    assert reply_safety.is_meaningful("ok")


# ── 3: true self-model ───────────────────────────────────────────

def test_describe_self_reports_real_architecture():
    d = self_model.describe_self()
    assert d["name"] == "Shree"
    assert d["has_offline_brain"] in (True, False)  # reflects real config
    assert "brain layer" in d["nature"]
    assert d["memory_types"] == 15


def test_self_knowledge_prompt_forbids_just_an_llm_disclaimer():
    p = self_model.self_knowledge_prompt()
    assert "NOT 'just a large language model'" in p
    assert "satya" in p.lower()
    assert "persistent brain" in p.lower()


def test_is_self_question_detects_identity_questions():
    assert self_model.is_self_question("who are you")
    assert self_model.is_self_question("do you have a brain")
    assert self_model.is_self_question("can you learn without llm")
    assert self_model.is_self_question("what is your date of birth")
    assert self_model.is_self_question("apna introduction dijiye")
    assert not self_model.is_self_question("add rate limiting to login")


def test_offline_reply_to_self_question_is_truthful_no_llm_denial():
    from app.brain.cognitive_loop import process
    result = process("do you have your own brain without LLM?", channel="chat")
    low = result["reply"].lower()
    assert "local brain" in low
    assert "just an llm" not in low or "not just" in low  # no generic denial


def test_self_question_prompt_includes_self_knowledge_block(monkeypatch):
    captured = {}

    class _Capture:
        name = "capture"
        def complete(self, system, prompt, max_tokens=800):
            captured["prompt"] = prompt
            return "ok"
    from app.brain import cognitive_loop as loop
    monkeypatch.setattr(loop, "get_provider", lambda: _Capture())
    loop.process("who are you really?", channel="chat")
    assert "TRUTHFUL SELF-KNOWLEDGE" in captured["prompt"]


# ── 4: action continuity memory ──────────────────────────────────

def test_direct_send_records_outbound_episodic(monkeypatch):
    from app.agents import tody_messaging

    class _FakeClient:
        def _post(self, path, data):
            return {"user": {"uuid": "u1", "username": "niva",
                             "display_name": "Niva"}}
        def start_direct(self, uuid):
            return {"conversation_id": 999}
        def send_message(self, conv, body):
            return {"message": {"id": 12345}}

    monkeypatch.setattr(tody_messaging, "get_client", lambda: _FakeClient())
    res = tody_messaging.send_direct("niva", "hello beta")
    assert res["sent"] is True

    from app.memory import dialogue_memory
    recalled = dialogue_memory.recall_person("Niva", limit=5)
    assert any("hello beta" in (r["content"] or "") for r in recalled)


# ── 5: memory dedup + rich recall ────────────────────────────────

def test_ensure_guardian_relationship_does_not_duplicate():
    from app.memory import relationship_memory
    a = relationship_memory.ensure_guardian_relationship()
    b = relationship_memory.ensure_guardian_relationship()
    c = relationship_memory.ensure_guardian_relationship()
    # Calling repeatedly must return the SAME id, not create new rows.
    assert a == b == c


def test_rich_recall_returns_content_not_just_titles():
    from app.memory import base_memory
    base_memory.add(memory_type="semantic", title="Niva is Rohit's daughter",
                    content="Niva is Rohit's daughter; she studies in school.",
                    related_person="Niva")
    hits = base_memory.recall_rich("Niva daughter", limit=3)
    assert hits
    assert any("daughter" in (h.content or "") for h in hits)


# ── 6: proactive people recall ───────────────────────────────────

def test_recall_person_returns_interactions():
    from app.memory import dialogue_memory
    dialogue_memory.remember_turn(
        channel="tody", conversation_id=241, direction="outbound_direct",
        body="hello beta, good morning", person="Niva", importance=7)
    recalled = dialogue_memory.recall_person("Niva", limit=5)
    assert recalled                         # found the interaction
    assert any("hello beta" in (r["content"] or "") for r in recalled)


def test_people_context_block_injected_when_person_mentioned(monkeypatch):
    from app.memory import dialogue_memory
    dialogue_memory.remember_turn(
        channel="tody", conversation_id=241, direction="outbound_direct",
        body="hello beta", person="Niva", importance=7)
    block = world_model.people_context_block("did niva reply to you?")
    assert "niva" in block.lower()
    assert "PEOPLE YOU MENTIONED" in block


def test_people_context_block_empty_when_no_person():
    assert world_model.people_context_block("what is 2+2") == ""


# ── 7: world model ───────────────────────────────────────────────

def test_known_people_includes_guardian():
    people = world_model.known_people()
    assert any("Rohit" in name for name in people)


def test_detect_mentioned_people_finds_handles():
    names = world_model.detect_mentioned_people("did @niva reply to @zarathakoo?")
    assert "niva" in [n.lower() for n in names]
    assert "zarathakoo" in [n.lower() for n in names]


def test_detect_mentioned_people_ignores_common_words():
    names = world_model.detect_mentioned_people("kya tum theek ho")
    assert names == []


def test_person_facts_reports_no_reply_yet():
    from app.memory import dialogue_memory
    dialogue_memory.remember_turn(
        channel="tody", conversation_id=555, direction="outbound_direct",
        body="good morning", person="TestPerson", importance=7)
    facts = world_model.person_facts("TestPerson")
    assert facts["known"] is True
    assert facts["outbound_count"] >= 1
    assert facts["inbound_count"] == 0  # no inbound → "no reply yet"


# ── 8: reflection loop on bad replies ────────────────────────────

def test_self_review_flags_empty_reply():
    from app.brain import self_review
    flags = self_review.review(message="hi", reply="", decision={"risk_tier": "low"})
    assert flags["was_empty"] is True
    assert flags["verdict"] == "needs_improvement"


def test_self_review_flags_prompt_leak():
    from app.brain import self_review
    leak = "I understood: Current date & time RIGHT NOW: Saturday. answer"
    flags = self_review.review(message="good morning", reply=leak,
                               decision={"risk_tier": "low"})
    assert flags["prompt_leaked"] is True
    assert flags["verdict"] == "needs_improvement"


def test_self_review_passes_good_reply():
    from app.brain import self_review
    flags = self_review.review(
        message="kaisi ho", reply="Main thik hoon Papa, aap batao kya kaam hai.",
        decision={"risk_tier": "low"})
    assert flags["verdict"] == "ok"
    assert not flags["was_empty"]
    assert not flags["prompt_leaked"]


def test_empty_reply_audited():
    from sqlalchemy import select
    from app.brain import self_review
    from app.db.models import CognitiveAuditLog, session_scope

    self_review.review(message="hi", reply="", decision={"risk_tier": "low"})
    with session_scope() as s:
        rows = s.scalars(
            select(CognitiveAuditLog).where(
                CognitiveAuditLog.action == "reply_quality_failure")
        ).all()
        n = len(rows)
    assert n >= 1


# ── integration: the never-silent guarantee end to end ───────────

def test_broken_llm_never_returns_empty(monkeypatch):
    """Even if the LLM returns empty, the reply must be non-empty and warm."""
    class _EmptyLLM:
        name = "nvidia"
        def complete(self, system, prompt, max_tokens=800):
            return ""  # model returns nothing
    from app.brain import cognitive_loop as loop
    monkeypatch.setattr(loop, "get_provider", lambda: _EmptyLLM())
    result = loop.process("kaisi ho tum", channel="chat")
    assert result["reply"].strip()
    assert len(result["reply"]) > 10
    assert "Papa" in result["reply"] or "thik" in result["reply"].lower()


def test_broken_llm_never_leaks_prompt(monkeypatch):
    """Even if the LLM echoes scaffolding, it must be stripped before TODY."""
    class _LeakyLLM:
        name = "nvidia"
        def complete(self, system, prompt, max_tokens=800):
            return ("I understood: Current date & time RIGHT NOW: Saturday. "
                    "never us. I will answer directly.")
    from app.brain import cognitive_loop as loop
    monkeypatch.setattr(loop, "get_provider", lambda: _LeakyLLM())
    result = loop.process("good morning", channel="chat")
    reply = result["reply"]
    assert "I understood" not in reply
    assert "Current date" not in reply
    assert len(reply) > 10  # warm fallback replaced the leak
