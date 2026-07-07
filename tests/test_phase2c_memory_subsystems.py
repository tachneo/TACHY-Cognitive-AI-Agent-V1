"""Phase 2C-selfverify (Phase 3): F3 memory subsystems + F5 mission follow-through.

The 10 memory stubs are now real typed wrappers over base_memory with recall
helpers, and failure_memory is wired into the self-review loop so Shree learns
from her own empty/leaked replies. The proactive loop now reports back to Rohit
on open conversation missions (she started missions but never reported back)."""
from __future__ import annotations

import pytest

from app.memory import (belief_memory, decision_memory, episodic_memory,
                        failure_memory, interest_memory, opportunity_memory,
                        procedural_memory, project_memory, risk_memory,
                        working_memory)


# ── base_memory.archive (used by working_memory) ─────────────────

def test_base_memory_archive_hides_from_search():
    from app.memory import base_memory
    mid = base_memory.add(memory_type="procedural", title="to-archive-test",
                          content="x", is_permanent=False)
    assert base_memory.archive(mid) is True
    # archived rows no longer appear in search
    hits = base_memory.search(memory_type="procedural", query="to-archive-test")
    assert not any(h.id == mid for h in hits)
    # archiving twice is a no-op
    assert base_memory.archive(mid) is False


# ── failure_memory (the big one for learning from mistakes) ──────

def test_failure_memory_remember_and_recall():
    failure_memory.remember_failure(
        kind="empty_reply", context="message=kaisi ho tum",
        lesson="give a real answer")
    fails = failure_memory.recall_recent_failures(kind="empty_reply", limit=5)
    assert fails
    assert any("empty_reply" == f["kind"] for f in fails)


def test_failure_memory_recall_similar():
    failure_memory.remember_failure(
        kind="prompt_leak", context="gold price question leaked scaffolding")
    similar = failure_memory.recall_similar_failures("gold price", limit=5)
    assert any("prompt_leak" in f["kind"] for f in similar)


def test_failure_count_increases():
    before = failure_memory.failure_count("empty_reply")
    failure_memory.remember_failure(kind="empty_reply", context="test count")
    after = failure_memory.failure_count("empty_reply")
    assert after >= before + 1


def test_self_review_stores_failure_to_failure_memory():
    """The learning-loop closure: when self_review flags an empty reply, it
    must store to failure_memory so Shree can recall_similar_failures later."""
    from app.brain import self_review
    self_review.review(message="tell me everything", reply="",
                       decision={"risk_tier": "low"})
    fails = failure_memory.recall_recent_failures(kind="empty_reply", limit=5)
    assert any("tell me everything" in (f["content"] or "") for f in fails)


def test_self_review_stores_prompt_leak_failure():
    from app.brain import self_review
    self_review.review(message="good morning",
                       reply="I understood: Current date & time RIGHT NOW",
                       decision={"risk_tier": "low"})
    fails = failure_memory.recall_recent_failures(kind="prompt_leak", limit=5)
    assert fails


# ── working_memory ───────────────────────────────────────────────

def test_working_memory_set_get_clear():
    cid = 99991
    working_memory.set_context(conversation_id=cid,
                               current_task="verify Rohit's code changes",
                               open_questions=["what did he change?"],
                               established=["he updated cognitive_loop"])
    ctx = working_memory.get_context(cid)
    assert ctx is not None
    assert "verify Rohit's code changes" in ctx["content"]
    working_memory.clear(cid)
    assert working_memory.get_context(cid) is None


def test_working_memory_set_replaces_prior():
    cid = 99992
    working_memory.set_context(conversation_id=cid, current_task="task A")
    working_memory.set_context(conversation_id=cid, current_task="task B")
    ctx = working_memory.get_context(cid)
    assert "task B" in ctx["content"]
    assert "task A" not in ctx["content"]
    working_memory.clear(cid)


# ── decision_memory ──────────────────────────────────────────────

def test_decision_memory_remember_and_recall():
    decision_memory.remember_decision(
        title="chose local sandbox over GitHub for verification",
        chosen="local sandbox", reason="faster, no token needed",
        outcome="worked")
    decs = decision_memory.recall_decisions("sandbox verification", limit=5)
    assert decs


# ── the other 6 subsystems: smoke remember + recall ──────────────

def test_episodic_memory_remember_and_recall():
    episodic_memory.remember_event(
        title="Rohit gave me self-verification tools",
        what="I can now read my own code and run my tests from chat")
    evs = episodic_memory.recall_events("verification tools", limit=5)
    assert evs


def test_interest_memory_remember_and_top():
    interest_memory.remember_interest(topic="cognitive architectures", score=9)
    tops = interest_memory.top_interests(n=10)
    assert any("cognitive" in t.lower() for t in tops)


def test_opportunity_memory_remember_and_recall():
    opportunity_memory.remember_opportunity(
        title="flat-fee ERP for small schools",
        detail="schools dislike per-student pricing")
    opps = opportunity_memory.recall_opportunities("flat fee", limit=5)
    assert opps


def test_risk_memory_remember_and_recall():
    risk_memory.remember_risk(
        title="unguarded run_bash in chat", severity=8,
        mitigation="strict allowlist + FORBIDDEN hard-block")
    risks = risk_memory.recall_risks("run_bash", limit=5)
    assert risks


def test_belief_memory_remember_and_recall():
    belief_memory.remember_belief(
        title="honesty over performance",
        statement="I must never claim a result I didn't verify",
        grounds="satya principle + Rohit's corrections")
    beliefs = belief_memory.recall_beliefs("honesty", limit=5)
    assert beliefs


def test_procedural_memory_remember_and_recall():
    procedural_memory.remember_procedure(
        name="verify-code-change",
        steps=["git_log", "git_diff", "read_file the changed file",
               "run_tests"],
        when_to_use="when Papa says he updated my code")
    procs = procedural_memory.recall_procedures("verify code", limit=5)
    assert procs


def test_project_memory_remember_and_recall():
    project_memory.remember_project_fact(
        project="BRAIN", fact="stack is Python 3.12 + FastAPI",
        detail="sqlite for dev, MySQL for prod")
    facts = project_memory.recall_project("BRAIN", limit=10)
    assert facts


# ── F5: proactive mission follow-through ─────────────────────────

def test_observe_mission_followup_returns_initiative_when_due(tmp_path, monkeypatch):
    from app.agents import proactive, conversation_mission
    # Seed a mission with enough exchanges to be due for a report.
    monkeypatch.setattr(conversation_mission, "_STATE", tmp_path / "m.json")
    conversation_mission.start("niva", "learn her interests",
                               target_conv_id=241, guardian_conv_id=135)
    # Bump exchanges past the report threshold (every 3).
    m = conversation_mission.for_conversation(241)
    m["exchanges"] = 3
    m["learned"] = ["she likes painting", "she studies in class 8"]
    conversation_mission._save({"by_target_conv": {"241": m},
                                 "by_username": {"niva": "241"}})
    item = proactive._observe_mission_followup()
    assert item is not None
    assert item.kind == "mission_followup"
    assert item.conversation_id == 135
    assert "niva" in item.text.lower()
    assert "painting" in item.text or "class 8" in item.text


def test_observe_mission_followup_none_when_not_due(tmp_path, monkeypatch):
    from app.agents import proactive, conversation_mission
    monkeypatch.setattr(conversation_mission, "_STATE", tmp_path / "m.json")
    conversation_mission.start("niva", "learn her interests",
                               target_conv_id=242, guardian_conv_id=135)
    # only 1 exchange, last_report_at_exchange=0 → 1-0 < 3 → not due
    assert proactive._observe_mission_followup() is None


def test_observe_includes_mission_followup_in_priority(tmp_path, monkeypatch):
    """observe() should be able to surface a mission follow-up."""
    from app.agents import proactive, conversation_mission
    monkeypatch.setattr(conversation_mission, "_STATE", tmp_path / "m.json")
    monkeypatch.setattr(proactive, "_QUEUE_PATH", tmp_path / "q.json")
    monkeypatch.setattr(proactive, "_guardian_conversation_id", lambda: 135)
    conversation_mission.start("niva", "learn her interests",
                               target_conv_id=243, guardian_conv_id=135)
    m = conversation_mission.for_conversation(243)
    m["exchanges"] = 3
    m["learned"] = ["she likes music"]
    conversation_mission._save({"by_target_conv": {"243": m},
                                 "by_username": {"niva": "243"}})
    item = proactive.observe()
    assert item is not None
    assert item.kind == "mission_followup"
