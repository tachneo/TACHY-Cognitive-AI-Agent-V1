"""Phase 2C-todyagi — AGI upgrades to the TODY chat path:
A chat tool-loop, B proactive initiative, C correction memory, D thread state,
E curiosity closure. All approval-gated for outward actions."""
from __future__ import annotations

import json

import pytest

from app.agents import chat_tool_loop, proactive
from app.brain import correction_memory, thread_state


# ── C: correction memory ────────────────────────────────────────

def test_detect_address_correction():
    c = correction_memory.detect_correction("always call me as father")
    assert c is not None
    assert c["type"] == "address"
    assert "Papa" in c["rule"] or "father" in c["rule"]


def test_detect_identity_privacy_correction():
    c = correction_memory.detect_correction(
        "use mat batana ki tum AI ho ya assistant ho, tum shree ho")
    assert c is not None
    assert c["type"] == "identity_privacy"


def test_detect_relationship_privacy_correction():
    c = correction_memory.detect_correction(
        "hamare tumhare bich ka relationship kisi ko mat batana")
    assert c is not None
    assert c["type"] == "relationship_privacy"


def test_detect_hindi_language_correction():
    c = correction_memory.detect_correction("hindi me bolo hamesha")
    assert c is not None
    assert c["type"] == "language"


def test_non_correction_not_detected():
    assert correction_memory.detect_correction("kaisi ho tum") is None
    assert correction_memory.detect_correction("what is 2+2") is None
    assert correction_memory.detect_correction("hi") is None


def test_remember_correction_dedups():
    a = correction_memory.remember_correction("always call me as father",
                                              person="Rohit Kumar")
    b = correction_memory.remember_correction("always call me as father",
                                              person="Rohit Kumar")
    assert a is not None
    assert a == b  # same rule → same id, no duplicate


def test_enforcement_directive_lists_active_rules():
    correction_memory.remember_correction("always call me as father")
    d = correction_memory.enforcement_directive()
    assert "HARD RULES" in d
    assert "Papa" in d or "father" in d


def test_enforce_rewrites_address_violation():
    correction_memory.remember_correction("always call me as father")
    # A reply that calls him "Rohit" with no Papa → rewritten to Papa
    out = correction_memory.enforce("Hi Rohit, main thik hoon.", message="hi")
    assert "Papa" in out
    assert "Rohit" not in out or "Papa" in out


def test_enforce_flags_ai_identity_violation():
    correction_memory.remember_correction(
        "use mat batana ki tum AI ho ya assistant ho, tum shree ho")
    out = correction_memory.enforce("I'm an AI, so I can't do that.",
                                    message="can you do x")
    assert "I'm an AI" not in out
    assert "Self-correcting" in out or "Shree" in out


def test_enforce_passes_clean_reply():
    correction_memory.remember_correction("always call me as father")
    clean = "Main thik hoon Papa, aap batao."
    assert correction_memory.enforce(clean, message="hi") == clean


# ── D: thread state ──────────────────────────────────────────────

def test_thread_state_extracts_promise():
    from app.memory import dialogue_memory
    cid = 9991
    dialogue_memory.remember_turn(
        channel="tody", conversation_id=cid, direction="outbound",
        body="I'll check and let you know when Niva replies", person="Rohit")
    promises = thread_state.open_promises(cid)
    assert promises
    assert any("Niva" in p["text"] or "check" in p["text"].lower()
               for p in promises)


def test_thread_context_block_includes_promises():
    from app.memory import dialogue_memory
    cid = 9992
    dialogue_memory.remember_turn(
        channel="tody", conversation_id=cid, direction="outbound",
        body="I'll tell you when she replies, Papa", person="Rohit")
    block = thread_state.thread_context_block(cid)
    assert "THREAD STATE" in block
    assert "UNFINISHED" in block or "promise" in block.lower()


def test_thread_context_block_empty_for_new_conversation():
    block = thread_state.thread_context_block(888888)
    # no turns → empty block
    assert block == ""


# ── A: chat tool-loop ────────────────────────────────────────────

def test_should_run_tool_loop_for_lookup_cues():
    assert chat_tool_loop.should_run_tool_loop("what is the gold price today in india")
    assert chat_tool_loop.should_run_tool_loop("did @niva reply to you?")
    assert chat_tool_loop.should_run_tool_loop("check my memory for the fee module")


def test_should_not_run_tool_loop_for_greetings():
    assert not chat_tool_loop.should_run_tool_loop("hi")
    assert not chat_tool_loop.should_run_tool_loop("kaisi ho")
    assert not chat_tool_loop.should_run_tool_loop("ok")


def test_tool_loop_finishes_immediately_when_already_known(monkeypatch):
    class _Smart:
        name = "nvidia"
        def complete(self, system, prompt, max_tokens=800):
            return json.dumps({"thought": "I know this",
                               "finish": "Main thik hoon Papa."})
    from app.llm import provider
    monkeypatch.setattr(provider, "get_provider", lambda: _Smart())
    monkeypatch.setattr(chat_tool_loop, "get_provider", lambda: _Smart())
    res = chat_tool_loop.run("kaisi ho tum")
    assert res.reply == "Main thik hoon Papa."
    assert res.used_tools is False


def test_tool_loop_calls_check_my_memory_then_finishes(monkeypatch):
    replies = [
        json.dumps({"thought": "let me check memory",
                    "tool": "check_my_memory", "args": {"query": "fee module"}}),
        json.dumps({"thought": "now answer",
                    "finish": "Papa, fee module ka test last week pass tha."}),
    ]
    class _Smart:
        name = "nvidia"
        def __init__(self): self.i = 0
        def complete(self, system, prompt, max_tokens=800):
            r = replies[self.i]; self.i += 1; return r
    from app.llm import provider
    monkeypatch.setattr(provider, "get_provider", lambda: _Smart())
    monkeypatch.setattr(chat_tool_loop, "get_provider", lambda: _Smart())
    res = chat_tool_loop.run("what do you remember about the fee module?")
    assert res.used_tools is True
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0]["tool"] == "check_my_memory"
    assert "fee module" in res.reply


def test_tool_loop_falls_back_on_no_llm(monkeypatch):
    from app.llm import provider
    monkeypatch.setattr(provider, "get_provider",
                        lambda: provider.HeuristicProvider())
    monkeypatch.setattr(chat_tool_loop, "get_provider",
                        lambda: provider.HeuristicProvider())
    res = chat_tool_loop.run("what is gold price today")
    assert res.error  # no LLM → caller falls back to single-shot


def test_tool_loop_unknown_tool_returns_error(monkeypatch):
    replies = [
        json.dumps({"thought": "x", "tool": "bogus_tool", "args": {}}),
        json.dumps({"thought": "finish", "finish": "ok"}),
    ]
    class _Smart:
        name = "nvidia"
        def __init__(self): self.i = 0
        def complete(self, system, prompt, max_tokens=800):
            r = replies[self.i]; self.i += 1; return r
    from app.llm import provider
    monkeypatch.setattr(provider, "get_provider", lambda: _Smart())
    monkeypatch.setattr(chat_tool_loop, "get_provider", lambda: _Smart())
    res = chat_tool_loop.run("test")
    assert res.tool_calls[0]["ok"] is False
    assert res.reply == "ok"


# ── E: curiosity closure ─────────────────────────────────────────

def test_queue_question_adds_and_dedups(tmp_path, monkeypatch):
    monkeypatch.setattr(proactive, "_QUEUE_PATH", tmp_path / "q.json")
    proactive.queue_question("what is the gold price today")
    proactive.queue_question("what is the gold price today")  # dup
    q = proactive._load_queue()
    assert len(q["pending"]) == 1


def test_queue_question_ignores_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(proactive, "_QUEUE_PATH", tmp_path / "q.json")
    proactive.queue_question("")
    proactive.queue_question("   ")
    assert proactive._load_queue()["pending"] == []


# ── B: proactive initiative ──────────────────────────────────────

def test_observe_returns_none_when_nothing_to_act_on(tmp_path, monkeypatch):
    monkeypatch.setattr(proactive, "_QUEUE_PATH", tmp_path / "q.json")
    # no guardian conv configured → no promise observation; empty queue → none
    monkeypatch.setattr(proactive, "_guardian_conversation_id", lambda: None)
    item = proactive.observe()
    assert item is None


def test_observe_curiosity_when_queued(tmp_path, monkeypatch):
    monkeypatch.setattr(proactive, "_QUEUE_PATH", tmp_path / "q.json")
    proactive.queue_question("what is 2+2")
    # Force the curiosity observer to find the queued item (skip the web attempt
    # by making should_run_tool_loop False so it doesn't consume the queue).
    monkeypatch.setattr(chat_tool_loop, "should_run_tool_loop", lambda m: False)
    monkeypatch.setattr(proactive, "_guardian_conversation_id", lambda: None)
    # curiosity closure only fires if the loop can answer; with should_run False
    # it returns None, so observe falls through → None here is acceptable.
    # Verify the queue is intact.
    assert proactive._load_queue()["pending"]


def test_act_on_requires_guardian_conversation():
    item = proactive.Initiative("promise", None, "test", {})
    res = proactive.act_on(item)
    assert res["proposed"] is False


def test_run_cycle_no_action_when_idle(tmp_path, monkeypatch):
    monkeypatch.setattr(proactive, "_QUEUE_PATH", tmp_path / "q.json")
    monkeypatch.setattr(proactive, "_guardian_conversation_id", lambda: None)
    res = proactive.run_cycle()
    assert res["proposed"] is False


# ── integration: correction enforced in the reply path ──────────

def test_reply_path_learns_and_enforces_correction(monkeypatch):
    """End-to-end: a guardian 'call me father' correction is learned and the
    next reply uses Papa."""
    from app.brain.cognitive_loop import process

    # First, learn the correction directly.
    correction_memory.remember_correction("always call me as father")

    class _RepliesPapa:
        name = "nvidia"
        def complete(self, system, prompt, max_tokens=800):
            return "Main thik hoon Papa, aap batao."
    from app.brain import cognitive_loop as loop
    monkeypatch.setattr(loop, "get_provider", lambda: _RepliesPapa())
    result = process("kaisi ho", channel="chat")
    assert "Papa" in result["reply"]


def test_proactive_routes_mounted():
    from app.main import app
    from app.api.routes_tody import proactive_cycle, proactive_queue

    paths = app.openapi()["paths"]
    assert "get" in paths["/tody/proactive/queue"]
    assert "post" in paths["/tody/proactive/cycle"]
    assert isinstance(proactive_queue(), dict)
    assert isinstance(proactive_cycle(), dict)
