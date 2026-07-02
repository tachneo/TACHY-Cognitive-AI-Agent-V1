"""Internal API authentication for the brain HTTP surface."""
from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from app.config import get_settings


def require_internal_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Require X-API-Key when INTERNAL_API_KEY is configured.

    Development can run without a key while the service is bound to localhost.
    Production must set INTERNAL_API_KEY; otherwise every protected endpoint
    fails closed.
    """
    settings = get_settings()
    expected = (settings.internal_api_key or "").strip()
    if not expected:
        if settings.app_env.lower() == "production":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="INTERNAL_API_KEY is not configured",
            )
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
