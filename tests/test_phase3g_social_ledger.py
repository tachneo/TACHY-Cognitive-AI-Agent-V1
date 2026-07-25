"""Phase 3G — social ledger: the truthful "who have you talked to?" answer.

25 Jul: Rohit asked who Shree talks to; she listed 2 people and said "aur koi
user nahi", omitting @khadim (214 messages, active that afternoon). She read as
a liar. She was BLIND — nothing fed her real conversation roster into a reply.
"""
import pytest

from app.brain import social_ledger as sl

_FAKE = [
    {"peer_username": "rohitsingh", "peer_name": "Rohit Kumar", "id": 135,
     "last_message_at": "2026-07-25T16:19:08+05:30", "unread_count": 0},
    {"peer_username": "khadim", "peer_name": "khadim", "id": 337,
     "last_message_at": "2026-07-25T14:02:42+05:30", "unread_count": 5},
    {"peer_username": "niva", "peer_name": "Niva", "id": 241,
     "last_message_at": "2026-07-23T11:32:21+05:30", "unread_count": 0},
    {"peer_username": None, "id": 374},  # deleted peer — must be skipped
]


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("SOCIAL_LEDGER_ENABLED", "true")
    monkeypatch.setenv("GUARDIAN_TODY_USERNAME", "rohitsingh")
    from app.config import get_settings
    get_settings.cache_clear()

    class _Client:
        def conversations(self, limit=20):
            return {"conversations": _FAKE}
    monkeypatch.setattr(sl, "get_client", lambda: _Client(), raising=False)
    import app.integrations.tody_client as tc
    monkeypatch.setattr(tc, "get_client", lambda: _Client())


def test_roster_pulls_real_partners_and_skips_non_people():
    people = {p["username"] for p in sl.roster()}
    assert {"rohitsingh", "khadim", "niva"} <= people
    assert None not in people and len(sl.roster()) == 3  # deleted peer skipped


@pytest.mark.parametrize("msg", [
    "abhi tak tumne kisse kisse baate ki hai?",
    "kya tum @khadim se baat nahi karti ho?",
    "kaun kaun se log hai jinse baat hui",
    "kitne logo se baat ki",
])
def test_roster_questions_detected(msg):
    assert sl.is_roster_question(msg) is True


def test_plain_chat_is_not_a_roster_question():
    for m in ("kaise ho tum", "good morning", "aaj kya kiya"):
        assert sl.is_roster_question(m) is False


def test_khadim_denial_is_now_impossible():
    # The exact challenge from 25 Jul. She must be TOLD khadim is real.
    block = sl.prompt_block("kya tum @khadim se baat nahi karti ho?")
    assert "@khadim" in block
    assert "YES" in block and "HAVE talked" in block


def test_who_do_you_talk_to_lists_everyone():
    block = sl.prompt_block("abhi tak tumne kisse kisse baat ki hai?")
    for u in ("rohitsingh", "khadim", "niva"):
        assert u in block
    assert "Papa" in block  # guardian tagged


def test_ledger_kill_switch(monkeypatch):
    monkeypatch.setenv("SOCIAL_LEDGER_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    assert sl.prompt_block("kisse baat ki hai?") == ""


def test_ledger_never_raises_on_api_failure(monkeypatch):
    import app.integrations.tody_client as tc

    class _Dead:
        def conversations(self, limit=20):
            raise RuntimeError("api down")
    monkeypatch.setattr(tc, "get_client", lambda: _Dead())
    assert sl.roster() == []
    assert sl.prompt_block("kisse baat ki hai?") == ""
