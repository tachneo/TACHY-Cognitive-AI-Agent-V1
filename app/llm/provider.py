"""Modular LLM provider interface.

The brain depends on the Provider protocol, never on a concrete vendor. Default
is the offline HeuristicProvider so the system runs with no API key. Set
LLM_PROVIDER=anthropic (+ LLM_API_KEY) in .env to use a real model.
"""
from __future__ import annotations

import re
import json
from typing import Protocol

import httpx

from app.config import get_settings
from app.llm.gen_state import record as _record_generation


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
        import time as _time
        last_exc: Exception | None = None
        # Retry 429 (rate limit) and 5xx/overloaded with backoff, honouring the
        # Retry-After header — the raw HTTP path has no SDK auto-retry.
        for attempt in range(5):
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
                timeout=90,
            )
            if resp.status_code in (429, 529, 500, 503):
                retry_after = resp.headers.get("retry-after")
                delay = float(retry_after) if (retry_after or "").replace(
                    ".", "", 1).isdigit() else min(2 ** attempt, 20)
                last_exc = httpx.HTTPStatusError(
                    f"{resp.status_code}", request=resp.request, response=resp)
                if attempt < 4:
                    _time.sleep(delay)
                    continue
            resp.raise_for_status()
            data = resp.json()
            return "".join(b.get("text", "") for b in data.get("content", []))
        if last_exc:
            raise last_exc
        return ""


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


class NvidiaProvider:
    """Calls NVIDIA NIM's OpenAI-compatible chat completions endpoint."""

    name = "nvidia"

    def __init__(self, api_key: str, model: str, base_url: str,
                 reasoning_budget: int = 16384, temperature: float = 1.0,
                 top_p: float = 0.95):
        self._key = api_key
        self._model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._reasoning_budget = reasoning_budget
        self._temperature = temperature
        self._top_p = top_p

    def complete(self, system: str, prompt: str, max_tokens: int = 800) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": self._temperature,
            "top_p": self._top_p,
            "max_tokens": max(max_tokens, self._reasoning_budget),
            "chat_template_kwargs": {"enable_thinking": True},
            "reasoning_budget": self._reasoning_budget,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self._key}",
            "content-type": "application/json",
        }
        final: list[str] = []
        finish: str | None = None
        with httpx.stream(
            "POST",
            self._url,
            headers=headers,
            json=payload,
            timeout=180,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                raw = line.removeprefix("data:").strip()
                if raw == "[DONE]":
                    break
                try:
                    chunk = json.loads(raw)
                except ValueError:
                    continue
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    content = _message_content(delta.get("content", ""))
                    if content:
                        final.append(content)
                    if choice.get("finish_reason"):
                        finish = choice["finish_reason"]
        text = "".join(final).strip()
        # A generation cut at max_tokens ends mid-word; sending it as-is reads
        # broken AND gets stored broken in memory. Trim back to the last
        # complete sentence (same guard the pool chat provider already has).
        truncated = finish == "length"
        if truncated and text:
            text = _trim_to_sentence(text)
        _record_generation(finish_reason=finish, truncated=truncated)
        return text


_SENTENCE_ENDS = (".", "!", "?", "।", "…", "\n")


def _trim_to_sentence(text: str) -> str:
    """A generation cut at max_tokens ends mid-word; sending it as-is reads
    broken (and gets stored broken in memory). Trim back to the last complete
    sentence when one exists past the halfway mark; else mark the cut."""
    cut = max(text.rfind(ch) for ch in _SENTENCE_ENDS)
    if cut >= len(text) // 2:
        return text[:cut + 1].rstrip()
    return text + "…"


class NvidiaChatProvider:
    """One model from the multi-LLM NVIDIA pool (DeepSeek/GLM/Gemma/MiniMax —
    OpenAI-compatible chat completions). Unlike NvidiaProvider (the nemotron
    reasoning stream), these are fast chat models: plain content streaming,
    finish_reason tracked, and a max_tokens cut is trimmed back to the last
    complete sentence instead of being sent (and remembered) mid-word."""

    def __init__(self, api_key: str, model: str, base_url: str, *,
                 temperature: float = 1.0, top_p: float = 0.95,
                 max_tokens_cap: int = 8192,
                 chat_template_kwargs: dict | None = None,
                 read_timeout: float = 240.0):
        self._key = api_key
        self._model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._temperature = temperature
        self._top_p = top_p
        self._cap = max_tokens_cap
        self._template_kwargs = chat_template_kwargs
        self._read_timeout = read_timeout
        self.name = f"nvidia/{model.split('/')[-1]}"

    def complete(self, system: str, prompt: str, max_tokens: int = 800) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": self._temperature,
            "top_p": self._top_p,
            "max_tokens": min(max(max_tokens, 256), self._cap),
            "stream": True,
        }
        if self._template_kwargs:
            payload["chat_template_kwargs"] = self._template_kwargs
        headers = {
            "Authorization": f"Bearer {self._key}",
            "content-type": "application/json",
            "Accept": "text/event-stream",
        }
        parts: list[str] = []
        finish: str | None = None
        # read timeout = first-token budget: an interactive purpose must fail
        # FAST when NVIDIA queues the model, so the fallback chain answers
        # instead of stalling the reply for minutes.
        with httpx.stream(
            "POST", self._url, headers=headers, json=payload,
            timeout=httpx.Timeout(self._read_timeout, connect=15),
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                raw = line.removeprefix("data:").strip()
                if raw == "[DONE]":
                    break
                try:
                    chunk = json.loads(raw)
                except ValueError:
                    continue
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    # only final content — never reasoning_content
                    content = _message_content(delta.get("content", ""))
                    if content:
                        parts.append(content)
                    if choice.get("finish_reason"):
                        finish = choice["finish_reason"]
        text = "".join(parts).strip()
        if finish == "length" and text:
            text = _trim_to_sentence(text)
        _record_generation(finish_reason=finish, truncated=(finish == "length"))
        return text


def _pool_template_kwargs(model: str) -> dict | None:
    """Per-model chat_template_kwargs. Pool models serve interactive/light
    purposes, so reasoning is kept OFF for speed (nemotron stays the deep
    thinker); ignored by models without a thinking template."""
    if "deepseek" in model:
        return {"thinking": False}
    if "gemma" in model:
        # diffusiongemma returns EMPTY content unless enable_thinking is true
        return {"enable_thinking": True}
    return None


# purpose → (model setting, key setting, max_tokens cap, first-token budget s)
# Interactive purposes get a short budget: a queued model fails fast and the
# caller's fallback chain answers. Vision/background can afford to wait.
_POOL = {
    "chat":   ("chat_nvidia_model", "chat_nvidia_key", 8192, 30.0),
    "social": ("social_nvidia_model", "social_nvidia_key", 4096, 30.0),
    "light":  ("light_nvidia_model", "light_nvidia_key", 2048, 20.0),
    "vision": ("vision_nvidia_model", "vision_nvidia_key", 8192, 240.0),
}
_pool_cache: dict[str, Provider] = {}


def pool_provider(purpose: str) -> Provider | None:
    """A model from the multi-LLM pool, or None when that purpose isn't
    configured (caller falls back). Purposes: chat (guardian conversation),
    social (everyone else), light (classify/rewrite/self-check), vision."""
    s = get_settings()
    if not s.llm_multi_enabled or purpose not in _POOL:
        return None
    model_attr, key_attr, cap, first_token_budget = _POOL[purpose]
    model = (getattr(s, model_attr) or "").strip()
    key = (getattr(s, key_attr) or "").strip()
    if not (model and key):
        return None
    cache_key = f"{purpose}:{model}"
    if cache_key not in _pool_cache:
        _pool_cache[cache_key] = NvidiaChatProvider(
            key, model, s.nvidia_base_url, max_tokens_cap=cap,
            chat_template_kwargs=_pool_template_kwargs(model),
            read_timeout=first_token_budget)
    return _pool_cache[cache_key]


def get_provider() -> Provider:
    s = get_settings()
    key = (s.llm_api_key or "").strip()
    if s.llm_provider == "anthropic" and key:
        return AnthropicProvider(key, s.llm_model)
    hf_key = (s.hf_token or "").strip()
    if s.llm_provider == "huggingface" and hf_key:
        return HuggingFaceProvider(hf_key, s.hf_model, s.hf_base_url)
    nvidia_key = (s.nvidia_api_key or "").strip()
    if s.llm_provider == "nvidia" and nvidia_key:
        return NvidiaProvider(
            nvidia_key,
            s.nvidia_model,
            s.nvidia_base_url,
            reasoning_budget=s.nvidia_reasoning_budget,
            temperature=s.nvidia_temperature,
            top_p=s.nvidia_top_p,
        )
    # 'glm' / 'local' providers plug in here in a later phase.
    return HeuristicProvider()


def get_chat_provider() -> Provider:
    """Provider for Shree's interactive chat replies — prefers Claude (warm,
    sharp, human) and falls back to the default provider. Background thinking
    (inner life, learning, curriculum) keeps using get_provider() so it never
    competes for the Claude rate limit."""
    s = get_settings()
    if s.chat_provider == "anthropic":
        key = (s.chat_anthropic_key or s.coding_anthropic_key
               or s.llm_api_key or "").strip()
        if key:
            return AnthropicProvider(key, s.chat_model)
    return pool_provider("chat") or get_provider()


def get_social_provider() -> Provider:
    """Provider for chats with people OTHER than the guardian — high-volume
    small talk on a fast pool model, so it never queues behind (or burns the
    limits of) the guardian's chat model."""
    return pool_provider("social") or get_chat_provider()


def get_light_provider() -> Provider:
    """Small fast pool model for internal micro-tasks (classification, query
    rewrites, fact-check synthesis) — cheap and quick, never the big models."""
    return pool_provider("light") or get_provider()


def get_coding_provider() -> Provider:
    """Provider for Shree's coding agent — prefers Claude (best agentic coding
    + tool use); falls back to the default chat provider when no Anthropic key
    is set, so coding always works (on NVIDIA today)."""
    s = get_settings()
    if s.coding_provider == "anthropic":
        key = (s.coding_anthropic_key or s.llm_api_key or "").strip()
        if key:
            return AnthropicProvider(key, s.coding_model)
    # No Claude key → fall back to the default provider, but if that's NVIDIA
    # give the coding tool loop a much smaller reasoning budget so it's snappy.
    nvidia_key = (s.nvidia_api_key or "").strip()
    if s.llm_provider == "nvidia" and nvidia_key:
        return NvidiaProvider(
            nvidia_key, s.nvidia_model, s.nvidia_base_url,
            reasoning_budget=s.coding_nvidia_reasoning_budget,
            temperature=s.nvidia_temperature, top_p=s.nvidia_top_p,
        )
    return get_provider()


def _message_content(content: object) -> str:
    if isinstance(content, list):
        return "".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict)
        )
    return str(content or "")


def _extract_user_message(prompt: str) -> str:
    # Take the LAST "User message (...): <text>" occurrence, up to a blank line.
    matches = re.findall(r"User message \([^)]*\):\s*(.*?)(?:\n\n|\Z)", prompt, re.S)
    if matches:
        return matches[-1].strip()
    lines = [line.strip() for line in prompt.splitlines() if line.strip()]
    return lines[-1] if lines else ""
