"""Modular LLM provider interface.

The brain depends on the Provider protocol, never on a concrete vendor. Default
is the offline HeuristicProvider so the system runs with no API key. Set
LLM_PROVIDER=anthropic (+ LLM_API_KEY) in .env to use a real model.
"""
from __future__ import annotations

from typing import Protocol

import httpx

from app.config import get_settings


class Provider(Protocol):
    name: str

    def complete(self, system: str, prompt: str, max_tokens: int = 800) -> str: ...


class HeuristicProvider:
    """Deterministic, offline fallback. Not intelligent — keeps the loop runnable
    and tests hermetic until a real model is configured."""

    name = "heuristic"

    def complete(self, system: str, prompt: str, max_tokens: int = 800) -> str:
        head = prompt.strip().splitlines()[0] if prompt.strip() else ""
        return (
            "[heuristic provider — no LLM key configured]\n"
            f"Understood request: {head[:200]}\n"
            "Set LLM_PROVIDER=anthropic and LLM_API_KEY in .env for real reasoning."
        )


class AnthropicProvider:
    """Calls the Anthropic Messages API. Model id comes from settings.llm_model
    (default claude-opus-4-8)."""

    name = "anthropic"
    _URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model: str):
        self._key = api_key
        self._model = model

    def complete(self, system: str, prompt: str, max_tokens: int = 800) -> str:
        resp = httpx.post(
            self._URL,
            headers={
                "x-api-key": self._key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self._model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return "".join(b.get("text", "") for b in data.get("content", []))


def get_provider() -> Provider:
    s = get_settings()
    key = (s.llm_api_key or "").strip()
    if s.llm_provider == "anthropic" and key:
        return AnthropicProvider(key, s.llm_model)
    # 'glm' / 'local' providers plug in here in a later phase.
    return HeuristicProvider()
