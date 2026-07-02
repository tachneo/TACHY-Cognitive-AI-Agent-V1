"""TODY live activation preflight checks.

All checks are explicit and pull-based. No service is started here.
"""
from __future__ import annotations

from app.agents import tody_agent, tody_worker
from app.config import get_settings
from app.safety.audit_logger import log_event


def preflight(*, check_login: bool = False) -> dict:
    """Return readiness for manually processing TODY messages.

    `check_login=True` may contact TODY through the configured client. The
    default is config/status only and performs no network request.
    """
    settings = get_settings()
    checks = {
        "app_env_set": bool(settings.app_env),
        "internal_api_key_configured": bool(settings.internal_api_key.strip()),
        "tody_api_base_configured": bool(settings.tody_api_base.strip()),
        "tody_email_configured": bool(settings.tody_email.strip()),
        "tody_password_configured": bool(settings.tody_password.strip()),
        "guardian_username_configured": bool(settings.guardian_tody_username.strip()),
        "guardian_email_configured": bool(settings.guardian_tody_email.strip()),
        "worker_idle": not tody_worker.status().get("locked"),
        "auto_reply_disabled": settings.tody_supervised_auto_reply is False,
    }
    login = {"checked": False}
    if check_login:
        login = {"checked": True}
        try:
            connected = tody_agent.connect()
            login.update(connected)
            checks["tody_login_ok"] = bool(connected.get("connected"))
        except Exception as exc:
            login.update({"connected": False, "error": type(exc).__name__})
            checks["tody_login_ok"] = False

    ready_for_manual = all(
        checks[k] for k in (
            "internal_api_key_configured",
            "tody_api_base_configured",
            "tody_email_configured",
            "tody_password_configured",
            "guardian_username_configured",
            "guardian_email_configured",
            "worker_idle",
        )
    )
    if check_login:
        ready_for_manual = ready_for_manual and checks.get("tody_login_ok", False)

    result = {
        "ready_for_manual_processing": ready_for_manual,
        "ready_for_background_worker": False,
        "background_worker_reason": "not enabled by code; requires explicit approval and service install",
        "checks": checks,
        "login": login,
        "next_step": (
            "Run /tody/activate/process-one with dry_run=true first."
            if ready_for_manual
            else "Fix failed checks before processing TODY messages."
        ),
    }
    log_event(
        "tody_activation_preflight",
        detail=f"check_login={check_login}; ready={ready_for_manual}",
        risk_tier="low",
    )
    return result


def process_one(*, dry_run: bool = True, conversation_limit: int = 10,
                message_limit: int = 10) -> dict:
    """Manual activation command: process at most one message."""
    result = tody_worker.poll_once(
        dry_run=dry_run,
        conversation_limit=conversation_limit,
        message_limit=message_limit,
    )
    result["manual_activation"] = True
    result["note"] = (
        "Dry run only; no draft or send performed."
        if dry_run else
        "Processed one message through the supervised TODY pipeline."
    )
    return result
