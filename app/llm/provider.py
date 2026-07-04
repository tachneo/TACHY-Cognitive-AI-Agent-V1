"""Modular LLM provider interface.

The brain depends on the Provider protocol, never on a concrete vendor. Default
is the offline HeuristicProvider so the system runs with no API key. Set
LLM_PROVIDER=anthropic (+ LLM_API_KEY) in .env to use a real model.
"""
from __future__ import annotations

import re
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
        message = _extract_user_message(prompt)
        lower = message.lower().strip()
        if lower in {"hi", "hii", "hello", "hey", "namaste"} or lower.startswith(
                ("how are you", "kaise ho")):
            return "Hey! Good to hear from you. What's on your mind?"
        if lower.startswith(("thank", "thanks")):
            return "Anytime — glad it helped."
        # Natural, honest, NEVER leaks the prompt or begs for an API key.
        return (
            "I hear you. My deeper reasoning model is offline at the moment, so "
            "I'm keeping this short — I've noted it and can go fuller once I'm "
            "back to full strength."
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


class HuggingFaceProvider:
    """Calls Hugging Face's OpenAI-compatible Inference Providers router."""

    name = "huggingface"

    def __init__(self, token: str, model: str, base_url: str):
        self._token = token
        self._model = model
        self._url = base_url.rstrip("/") + "/chat/completions"

    def complete(self, system: str, prompt: str, max_tokens: int = 800) -> str:
        resp = httpx.post(
            self._url,
            headers={
                "Authorization": f"Bearer {self._token}",
                "content-type": "application/json",
            },
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.3,
            },
            timeout=90,
        )
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return ""
        msg = choices[0].get("message") or {}
        content = msg.get("content", "")
        if isinstance(content, list):
            return "".join(part.get("text", "") for part in content if isinstance(part, dict))
        return str(content)


def get_provider() -> Provider:
    s = get_settings()
    key = (s.llm_api_key or "").strip()
    if s.llm_provider == "anthropic" and key:
        return AnthropicProvider(key, s.llm_model)
    hf_key = (s.hf_token or "").strip()
    if s.llm_provider == "huggingface" and hf_key:
        return HuggingFaceProvider(hf_key, s.hf_model, s.hf_base_url)
    # 'glm' / 'local' providers plug in here in a later phase.
    return HeuristicProvider()


def _extract_user_message(prompt: str) -> str:
    # Take the LAST "User message (...): <text>" occurrence, up to a blank line.
    matches = re.findall(r"User message \([^)]*\):\s*(.*?)(?:\n\n|\Z)", prompt, re.S)
    if matches:
        return matches[-1].strip()
    lines = [line.strip() for line in prompt.splitlines() if line.strip()]
    return lines[-1] if lines else ""
