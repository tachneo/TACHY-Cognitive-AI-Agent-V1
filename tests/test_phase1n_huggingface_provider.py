"""Phase 1N — Hugging Face LLM provider."""


def test_huggingface_provider_selected_when_configured(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("LLM_PROVIDER", "huggingface")
    monkeypatch.setenv("HF_TOKEN", "test-token")
    monkeypatch.setenv("HF_MODEL", "openai/gpt-oss-120b:fastest")
    get_settings.cache_clear()

    from app.llm.provider import get_provider

    provider = get_provider()
    assert provider.name == "huggingface"


def test_huggingface_provider_uses_openai_compatible_payload(monkeypatch):
    from app.llm.provider import HuggingFaceProvider

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "hello"}}]}

    def fake_post(url, headers, json, timeout):
        captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr("app.llm.provider.httpx.post", fake_post)

    provider = HuggingFaceProvider(
        "token", "openai/gpt-oss-120b:fastest", "https://router.huggingface.co/v1"
    )
    out = provider.complete("system", "prompt", max_tokens=12)

    assert out == "hello"
    assert captured["url"] == "https://router.huggingface.co/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer token"
    assert captured["json"]["model"] == "openai/gpt-oss-120b:fastest"
    assert captured["json"]["messages"][0]["role"] == "system"
    assert captured["json"]["max_tokens"] == 12
