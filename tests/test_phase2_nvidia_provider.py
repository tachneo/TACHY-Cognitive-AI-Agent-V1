"""NVIDIA NIM LLM provider."""


def test_nvidia_provider_selected_when_configured(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.setenv("NVIDIA_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")
    get_settings.cache_clear()

    from app.llm.provider import get_provider

    provider = get_provider()
    assert provider.name == "nvidia"


def test_nvidia_provider_uses_openai_compatible_payload(monkeypatch):
    from app.llm.provider import NvidiaProvider

    captured = {}

    class FakeStreamResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def raise_for_status(self):
            return None

        def iter_lines(self):
            yield 'data: {"choices":[{"delta":{"reasoning_content":"private reasoning"}}]}'
            yield 'data: {"choices":[{"delta":{"content":"final"}}]}'
            yield 'data: {"choices":[{"delta":{"content":" answer"}}]}'
            yield "data: [DONE]"

    def fake_stream(method, url, headers, json, timeout):
        captured.update({
            "method": method,
            "url": url,
            "headers": headers,
            "json": json,
            "timeout": timeout,
        })
        return FakeStreamResponse()

    monkeypatch.setattr("app.llm.provider.httpx.stream", fake_stream)

    provider = NvidiaProvider(
        "token",
        "nvidia/nemotron-3-ultra-550b-a55b",
        "https://integrate.api.nvidia.com/v1",
        reasoning_budget=4096,
        temperature=1,
        top_p=0.95,
    )
    out = provider.complete("system", "prompt", max_tokens=12)

    assert out == "final answer"
    assert captured["method"] == "POST"
    assert captured["url"] == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer token"
    assert captured["json"]["model"] == "nvidia/nemotron-3-ultra-550b-a55b"
    assert captured["json"]["messages"][0]["role"] == "system"
    assert captured["json"]["max_tokens"] == 4096
    assert captured["json"]["chat_template_kwargs"] == {"enable_thinking": True}
    assert captured["json"]["reasoning_budget"] == 4096
    assert captured["json"]["stream"] is True
    assert captured["timeout"] >= 180
