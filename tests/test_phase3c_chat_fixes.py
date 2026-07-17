"""Phase 3C — the 11 Jul chat-failure fixes.

Three real failures from Rohit's chat, each now covered:
  1. reminders never created a row (gemma returned empty) → deterministic parser
  2. the false-send guard swapped legit reminder replies for an off-topic
     "message @username" template → scoped to real third-party sends
  3. she couldn't like/reply/comment on TODY chats → social action layer
"""
import datetime as dt

import pytest


# ── Fix #1: deterministic reminder parser ────────────────────────
from app.brain import prospective_memory as pm

_NOW = dt.datetime(2026, 7, 11, 10, 0, tzinfo=pm._IST)


@pytest.mark.parametrize("msg,hh,mm,day", [
    ("Yes remind me at 10:10 am", 10, 10, 11),
    ("mujhe 10:35 ko remind kar ki nahane jana hai", 10, 35, 11),
    ("remind me at 5 pm", 17, 0, 11),
    ("10 minute baad yaad dilana", 10, 10, 11),
    ("2 ghante baad ping karo", 12, 0, 11),
    ("kal subah yaad dilana", 8, 0, 12),
    ("shaam 5 baje remind me", 17, 0, 11),
    ("raat ko yaad dilana", 21, 0, 11),
])
def test_deterministic_parse_hits(msg, hh, mm, day):
    due = pm._deterministic_parse(msg, _NOW)
    assert due is not None, msg
    ist = due.replace(tzinfo=dt.UTC).astimezone(pm._IST)
    assert (ist.hour, ist.minute, ist.day) == (hh, mm, day), msg


def test_deterministic_parse_ignores_non_time():
    assert pm._deterministic_parse("hello kaise ho", _NOW) is None
    assert pm._deterministic_parse("good morning shree", _NOW) is None


def test_extract_creates_row_without_any_model(monkeypatch):
    # The whole point: reminders must NOT depend on the light model. Force the
    # model to raise; the deterministic path must still create the row.
    def boom(prompt):
        raise RuntimeError("model down")
    monkeypatch.setattr(pm, "_light_complete", boom)
    r = pm.extract("remind me at 5 pm to call", 135,
                   source_message_id="m1", person="Rohit Kumar", is_guardian=True)
    assert r["created"] is True
    assert "id" in r


def test_extract_still_guardian_only(monkeypatch):
    r = pm.extract("remind me at 5 pm", 999, person="komal", is_guardian=False)
    assert r["created"] is False


# ── Fix #2: scoped false-send guard ──────────────────────────────
from app.agents import tody_agent as ta


@pytest.mark.parametrize("reply,intent,expected", [
    ("Main tumhe 10:10 baje notification bhej dungi", None, False),   # reminder→Papa
    ("10:10 pe ping kar dungi, reminder set", None, False),
    ("main check karti hoon kyu reminder fail hua", None, False),
    ("Haan main @niva ko message bhej dungi", None, True),            # real 3rd party
    ("Main unhe bata dungi", "third_party_action", True),
])
def test_third_party_send_scoping(reply, intent, expected):
    assert ta._is_third_party_send(reply, "", intent) is expected


# ── Fix #3: TODY social action parser ────────────────────────────
from app.agents import tody_social_actions as tsa


def test_social_react_variants():
    assert tsa.parse_command("like @niva ka message")["action"] == "react"
    assert tsa.parse_command("@niva ke message pe dil laga do")["emoji"] == "❤️"


def test_social_reply_and_post_and_star():
    r = tsa.parse_command("reply @niva: haan aa jao")
    assert r["action"] == "reply" and r["user"] == "niva" and "aa jao" in r["body"]
    assert tsa.parse_command("post: aaj accha din tha")["action"] == "post"
    assert tsa.parse_command("star @niva ka message")["action"] == "star"


def test_social_ignores_plain_chat():
    assert tsa.parse_command("kaise ho tum") is None
    assert tsa.parse_command("good morning") is None
    assert tsa.parse_command("ispe comment batao kya karna hai") is None


def test_social_post_returns_created_post_evidence(monkeypatch):
    class FakeClient:
        def create_post(self, body):
            return {"post": {"id": 321, "body": body}}

    monkeypatch.setattr(tsa, "get_client", lambda: FakeClient())
    out = tsa.do_post("skill practice report")
    assert out["ok"] is True
    assert out["post_id"] == 321
    assert out["body"] == "skill practice report"


def test_social_actions_registered_in_action_engine():
    from app.brain import action_engine
    names = {s["name"] for s in action_engine.registry()}
    assert {"tody_react", "tody_reply", "tody_post"} <= names
    # Outward social actions are gated (not low-risk auto-run).
    reg = action_engine.REGISTRY
    assert reg["tody_reply"].risk_tier == "high"
    assert reg["tody_post"].risk_tier == "high"
