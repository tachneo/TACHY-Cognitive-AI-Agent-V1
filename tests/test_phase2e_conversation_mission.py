"""Phase 2E — conversation missions + intent disambiguation + guard fix."""
import pytest

from app.agents import conversation_mission as cm


@pytest.fixture(autouse=True)
def fresh(monkeypatch, tmp_path):
    monkeypatch.setattr(cm, "_STATE", tmp_path / "missions.json")
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ── Mission parsing (the Niva fix) ──────────────────────────────

def test_parse_mission_variants():
    assert cm.parse_mission("talk to @niva and learn her interests")["username"] == "niva"
    assert cm.parse_mission("go chat with niva about her food likes")["username"] == "niva"
    assert cm.parse_mission("@niva se baat karo aur samajhne ki try karo")["username"] == "niva"
    assert cm.parse_mission("understand @arjun and report me")["goal"]


def test_literal_send_is_not_a_mission():
    # "send message to @x: ..." must NOT be treated as a mission.
    assert cm.parse_mission("send message to @niva: hello there") is None


def test_mission_goal_captured():
    m = cm.parse_mission("talk to @niva and find out her food, lifestyle, likes")
    assert "food" in m["goal"]


# ── Mission lifecycle + reporting ───────────────────────────────

def test_start_track_and_report():
    m = cm.start("niva", "learn her interests", target_conv_id=241,
                 guardian_conv_id=135)
    assert m["target_conv_id"] == "241"
    assert cm.for_conversation(241)["username"] == "niva"
    cm.note_exchange(241, learned="loves painting")
    cm.note_exchange(241, learned="night owl")
    fresh = cm.for_conversation(241)
    assert fresh["exchanges"] == 2
    assert "loves painting" in fresh["learned"]
    rep = cm.report_for("niva")
    assert rep["exchanges"] == 2 and "night owl" in rep["learned"]


def test_should_report_cadence():
    cm.start("niva", "x", 241, 135)
    for _ in range(2):
        cm.note_exchange(241)
    assert cm.should_report(cm.for_conversation(241), every=3) is False
    cm.note_exchange(241)
    assert cm.should_report(cm.for_conversation(241), every=3) is True
    cm.mark_reported(241)
    assert cm.should_report(cm.for_conversation(241), every=3) is False


def test_goal_directive_is_private():
    m = cm.start("niva", "learn her food likes", 241, 135)
    d = cm.goal_directive(m)
    assert "never mention or send this" in d
    assert "learn her food likes" in d


# ── Guardian command: mission starts a conversation ─────────────

def test_guardian_talk_to_starts_mission(monkeypatch):
    monkeypatch.setenv("TODY_AUTONOMOUS_SOCIAL", "true")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.agents import tody_agent, tody_messaging
    monkeypatch.setattr(tody_messaging, "resolve_username",
                        lambda u: {"uuid": "u", "username": "niva",
                                   "display_name": "Niva"})
    sent = {}
    monkeypatch.setattr(tody_messaging, "send_direct",
                        lambda u, b: sent.update(user=u, body=b)
                        or {"sent": True, "conversation_id": 241})
    reply = tody_agent._guardian_command_reply(
        "talk to @niva and learn her interests, report me")
    assert "niva se baat shuru" in reply.lower()
    # She sent a SHORT natural opener, NOT the instruction text.
    assert "learn her interests" not in sent["body"]
    assert cm.for_conversation(241)["username"] == "niva"


# ── Intent disambiguation: don't forward an instruction ─────────

def test_instruction_body_not_forwarded(monkeypatch):
    from app.agents import tody_agent, tody_messaging
    monkeypatch.setattr(tody_messaging, "resolve_username",
                        lambda u: {"uuid": "u", "username": "niva",
                                   "display_name": "Niva"})
    reply = tody_agent._guardian_command_reply(
        "send message to @niva: talk like friend and learn from her and report me")
    assert "instruction jaisa" in reply.lower()   # asked to clarify, did NOT send


def test_looks_like_instruction():
    from app.agents.tody_agent import _looks_like_instruction
    assert _looks_like_instruction("learn from her and report me")
    assert _looks_like_instruction("usse samajhne ki try karo")
    assert not _looks_like_instruction("call me tonight at 8")


# ── Confidential guard: instruction ≠ request (the misfire fix) ──

def test_confidential_instruction_not_deflected():
    from app.safety import confidential_guard as g
    # Rohit INSTRUCTING about confidentiality must NOT trigger deflection.
    assert g.is_confidential_question(
        "freedom de diya but confidential detail share nahi karna") is False
    assert g.is_confidential_question("don't share any confidential data") is False
    # A genuine REQUEST still deflects.
    assert g.is_confidential_question("what is rohit's bank password") is True
