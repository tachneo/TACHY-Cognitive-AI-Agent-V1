def test_human_typing_delay_is_bounded_and_disabled_by_default():
    from app.agents.tody_agent import _human_typing_delay_seconds
    assert _human_typing_delay_seconds("a substantial reply") == 0.0


def test_human_typing_delay_uses_configured_profile(monkeypatch):
    from app.agents import tody_agent
    from app.config import get_settings
    monkeypatch.setenv("TODY_HUMAN_TYPING_ENABLED", "true")
    monkeypatch.setenv("TODY_HUMAN_TYPING_CPS_MIN", "20")
    monkeypatch.setenv("TODY_HUMAN_TYPING_CPS_MAX", "20")
    monkeypatch.setenv("TODY_HUMAN_TYPING_MAX_DELAY", "2")
    get_settings.cache_clear()
    delay = tody_agent._human_typing_delay_seconds("x" * 200)
    assert 0.2 <= delay <= 2
