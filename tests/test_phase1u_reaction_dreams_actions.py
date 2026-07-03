"""Phase 1U/1V/1E — reaction learning, dream recombination, action engine."""
import datetime as dt

import pytest

from app.agents import tody_agent
from app.brain import action_engine, inner_life


@pytest.fixture(autouse=True)
def fresh_settings():
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _ist(hour: int) -> dt.datetime:
    tz = dt.timezone(dt.timedelta(hours=5, minutes=30))
    return dt.datetime(2026, 7, 3, hour, 0, tzinfo=tz)


# ── 1U: reaction learning ───────────────────────────────────────

def test_positive_reaction_raises_share_score():
    inner_life.record_share("I had a thought about ERP security.")
    out = inner_life.observe_reaction("wow, great thought! keep it up")
    assert out["reaction"] == "positive"
    assert out["share_score"] > 0.5


def test_negative_reaction_drops_score_and_remembers():
    inner_life.record_share("Another thought.")
    out = inner_life.observe_reaction("stop, don't send me so many messages")
    assert out["reaction"] == "negative"
    assert out["share_score"] < 0.5
    from app.memory import base_memory
    hits = base_memory.search(memory_type="behavior", project="INNER_LIFE")
    assert hits and "negative" in hits[0].title


def test_ignored_share_decays_score():
    inner_life.record_share("First thought.")   # never answered
    inner_life.record_share("Second thought.")  # supersedes → first = ignored
    assert inner_life._load_state()["share_score"] < 0.5


def test_reaction_scored_only_once():
    inner_life.record_share("One thought.")
    inner_life.observe_reaction("great!")
    assert inner_life.observe_reaction("great again!")["reaction"] is None


def test_low_score_caps_shares_at_one():
    state = inner_life._load_state()
    state["share_score"] = 0.1
    state["share_queue"] = ["a", "b", "c"]
    inner_life._save_state(state)
    sent = [inner_life.maybe_share(now=_ist(11))["share"] for _ in range(3)]
    assert sum(1 for s in sent if s) == 1


# ── 1V: dream recombination ─────────────────────────────────────

def test_consolidate_dreams_and_queues_share(monkeypatch):
    from app.memory import base_memory
    base_memory.add(memory_type="semantic", title="ERP fee dedup lesson",
                    content="store fees deduped", project="ERP")
    base_memory.add(memory_type="emotional", title="Joy about TODY growth",
                    content="tody community growing", project="TODY")

    class FakeProvider:
        name = "fake"

        def complete(self, system, prompt, max_tokens=300):
            if "DREAM MODE" in prompt:
                return ("What if TODY's community energy could promote the "
                        "school ERP through parent groups?")
            return "Consolidation summary."

    monkeypatch.setattr(inner_life, "get_provider", lambda: FakeProvider())
    out = inner_life.consolidate()
    assert out["dream"]["idea"] and out["dream"]["memory_id"]
    hits = base_memory.search(memory_type="opportunity", project="INNER_LIFE")
    assert hits and "Dream idea" in hits[0].title
    assert any("idea" in s for s in inner_life._load_state()["share_queue"])


def test_dream_none_is_not_stored(monkeypatch):
    class FakeProvider:
        name = "fake"

        def complete(self, system, prompt, max_tokens=300):
            return "NONE" if "DREAM MODE" in prompt else "Summary."

    monkeypatch.setattr(inner_life, "get_provider", lambda: FakeProvider())
    out = inner_life.consolidate()
    assert out["dream"]["idea"] is None


# ── 1E: action engine ───────────────────────────────────────────

def test_low_risk_action_executes_immediately(monkeypatch):
    from app.brain import web_learning
    monkeypatch.setattr(web_learning, "explore",
                        lambda topic=None, **kw: {"topic": topic, "learned": True})
    out = action_engine.propose("learn_topic", {"topic": "webhooks"})
    assert out["executed"] is True
    assert out["result"]["learned"] is True
    from app.memory import base_memory
    hits = base_memory.search(memory_type="decision", project="AUTOMATION")
    assert hits and "learn_topic" in hits[0].title


def test_unknown_action_rejected():
    out = action_engine.propose("rm_rf_everything", {})
    assert out["accepted"] is False


def test_high_risk_action_waits_for_approval():
    out = action_engine.propose("send_tody_message",
                                {"conversation_id": 135, "body": "hi"})
    assert out["accepted"] is True and out["executed"] is False
    approval_id = out["approval"]["id"]
    # cannot run while pending
    assert action_engine.execute_approved(approval_id)["executed"] is False
    from app.safety import approvals
    approvals.respond(approval_id, approved=True)
    done = action_engine.execute_approved(approval_id)
    assert done["executed"] is True
    assert done["result"]["queued"] is True  # delegated to send approval flow


def test_guardian_chat_commands(monkeypatch):
    # queue a gated action
    out = action_engine.propose("consolidate_memory", {})
    approval_id = out["approval"]["id"]

    listing = tody_agent._guardian_command_reply("pending")
    assert f"#{approval_id}" in listing

    monkeypatch.setattr(inner_life, "consolidate",
                        lambda: {"lesson_id": 1, "archived": 0})
    done = tody_agent._guardian_command_reply(f"approve {approval_id}")
    assert "Approved and done: consolidate_memory" in done

    again = tody_agent._guardian_command_reply(f"approve {approval_id}")
    assert "already approved" in again

    out2 = action_engine.propose("consolidate_memory", {})
    rejected = tody_agent._guardian_command_reply(f"reject {out2['approval']['id']}")
    assert "Rejected" in rejected
    assert tody_agent._guardian_command_reply("normal chat message") is None


def test_guardian_command_bypasses_llm(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("LLM path must not run for commands")

    monkeypatch.setattr(tody_agent, "process", boom)
    monkeypatch.setattr(tody_agent, "request_send",
                        lambda *a, **k: {"approval": {"id": 99}})
    out = tody_agent.draft_reply_to_message(
        901, "pending", sender={"username": "rohitsingh"},
        message_id="cmd-1", auto_send_guardian=False)
    assert "pending" in out["draft"].lower() or "approvals" in out["draft"].lower()


def test_actions_routes_mounted():
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as client:
        reg = client.get("/actions/registry")
        assert reg.status_code == 200
        names = {a["name"] for a in reg.json()["actions"]}
        assert {"learn_topic", "send_tody_message", "create_goal"} <= names
