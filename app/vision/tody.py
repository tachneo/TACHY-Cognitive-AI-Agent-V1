"""Explicit, bounded vision adapter for TODY image attachments."""
from __future__ import annotations

import base64
import httpx
from app.config import get_settings


def analyze_image(image: bytes, mime_type: str, prompt: str = "Describe this image accurately.") -> dict:
    settings = get_settings()
    if not settings.tody_vision_enabled:
        return {"ok": False, "reason": "vision_disabled", "answer": None}
    if len(image) > settings.tody_vision_max_bytes:
        return {"ok": False, "reason": "image_too_large", "answer": None}
    key = settings.vision_nvidia_key or settings.nvidia_api_key
    if not key:
        return {"ok": False, "reason": "vision_provider_not_configured", "answer": None}
    data_url = f"data:{mime_type};base64,{base64.b64encode(image).decode('ascii')}"
    payload = {"model": settings.tody_vision_model, "messages": [{"role": "user", "content": [
        {"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": data_url}}
    ]}], "max_tokens": 1200, "temperature": 0.2, "top_p": 0.95, "stream": False}
    response = httpx.post(settings.nvidia_base_url.rstrip('/') + '/chat/completions',
                          headers={"Authorization": f"Bearer {key}", "content-type": "application/json"},
                          json=payload, timeout=90)
    response.raise_for_status()
    body = response.json(); choices = body.get("choices") or []
    answer = ((choices[0].get("message") or {}).get("content") if choices else "") or ""
    return {"ok": bool(answer.strip()), "reason": None if answer.strip() else "empty_provider_response", "answer": answer.strip(), "model": settings.tody_vision_model}
