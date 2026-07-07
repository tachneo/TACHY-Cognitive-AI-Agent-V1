"""Phase 2F — Claude chat provider split (chat = Claude, background = default)."""
import pytest


@pytest.fixture(autouse=True)
def fresh():
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_chat_provider_prefers_anthropic_with_key(monkeypatch):
    monkeypatch.setenv("CHAT_PROVIDER", "anthropic")
    monkeypatch.setenv("CHAT_ANTHROPIC_KEY", "sk-ant-test")
    monkeypatch.setenv("CHAT_MODEL", "claude-sonnet-5")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.llm.provider import get_chat_provider
    p = get_chat_provider()
    assert p.name == "anthropic"
    assert p._model == "claude-sonnet-5"


def test_chat_provider_reuses_coding_key(monkeypatch):
    monkeypatch.setenv("CHAT_PROVIDER", "anthropic")
    monkeypatch.setenv("CHAT_ANTHROPIC_KEY", "")
    monkeypatch.setenv("CODING_ANTHROPIC_KEY", "sk-ant-coding")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.llm.provider import get_chat_provider, AnthropicProvider
    p = get_chat_provider()
    assert isinstance(p, AnthropicProvider)


def test_chat_provider_falls_back_without_key(monkeypatch):
    monkeypatch.setenv("CHAT_PROVIDER", "anthropic")
    monkeypatch.setenv("CHAT_ANTHROPIC_KEY", "")
    monkeypatch.setenv("CODING_ANTHROPIC_KEY", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_PROVIDER", "heuristic")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.llm.provider import get_chat_provider
    assert get_chat_provider().name == "heuristic"


def test_chat_provider_default_stays_on_default(monkeypatch):
    # chat_provider=default → uses get_provider() (no Claude even if key present)
    monkeypatch.setenv("CHAT_PROVIDER", "default")
    monkeypatch.setenv("CODING_ANTHROPIC_KEY", "sk-ant-x")
    monkeypatch.setenv("LLM_PROVIDER", "heuristic")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.llm.provider import get_chat_provider
    assert get_chat_provider().name == "heuristic"


def test_background_thinking_stays_off_claude(monkeypatch):
    # inner_life / web_learning use get_provider(), NOT get_chat_provider(),
    # so they never draw on the Claude rate limit.
    monkeypatch.setenv("CHAT_PROVIDER", "anthropic")
    monkeypatch.setenv("CODING_ANTHROPIC_KEY", "sk-ant-x")
    monkeypatch.setenv("LLM_PROVIDER", "heuristic")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.llm.provider import get_provider, get_chat_provider
    assert get_provider().name == "heuristic"        # background
    assert get_chat_provider().name == "anthropic"   # chat
