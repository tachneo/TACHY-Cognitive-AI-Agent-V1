"""TODY worker loop.

Default mode is dry-run. Live processing requires both `--live` and
`TODY_WORKER_LIVE_CONFIRM=YES` so an accidental service start cannot send.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
from pathlib import Path
import sys
import time

from app.agents import tody_agent
from app.agents import tody_activation
from app.agents import tody_worker
from app.integrations.tody_client import get_client

DEFAULT_WORKER_INTERVAL = 90
DEFAULT_FAST_REPLY_INTERVAL = 5
DEFAULT_ERROR_BACKOFF = 1800
DEFAULT_RATE_LIMIT_BACKOFF = 3600


def _env_true(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _fast_reply_conversation_id(cli_value: str | None = None) -> int | None:
    """Return the known active guardian conversation for low-latency polling."""
    candidates = [
        cli_value,
        os.getenv("TODY_FAST_REPLY_CONVERSATION_ID"),
        os.getenv("TODY_DAILY_CURIOSITY_CONVERSATION_ID"),
        os.getenv("TODY_DAILY_GROWTH_CONVERSATION_ID"),
    ]
    for value in candidates:
        text = str(value or "").strip()
        if text.isdigit():
            return int(text)
    return None


def maybe_update_presence(*, dry_run: bool) -> dict:
    """Refresh TODY online/last-seen state through chat/poll.php.

    chat-tachy updates `global_users.last_seen_at` only from the poll endpoint,
    not from messages.php. This heartbeat lets the brain show as online while
    the live worker is running. Presence failure is UX-only and must not block
    message processing.
    """
    if dry_run or not _env_enabled("TODY_PRESENCE_HEARTBEAT_ENABLED", default=True):
        return {"presence_heartbeat": "disabled"}
    try:
        data = get_client().presence_heartbeat()
        return {
            "presence_heartbeat": "ok",
            "presence_count": len(data.get("presence", []) or []),
            "typing_count": len(data.get("typing", []) or []),
        }
    except Exception as exc:
        return {
            "presence_heartbeat": "failed",
            "error": type(exc).__name__,
        }


def maybe_send_daily_growth_report(*, dry_run: bool) -> dict:
    """Send Rohit's daily growth report once per UTC date when enabled."""
    if dry_run or not _env_true("TODY_DAILY_GROWTH_REPORT"):
        return {"daily_growth_report": "disabled"}

    conversation_id = os.getenv("TODY_DAILY_GROWTH_CONVERSATION_ID", "").strip()
    if not conversation_id.isdigit():
        return {"daily_growth_report": "missing_conversation_id"}

    today = dt.datetime.now(dt.UTC).date().isoformat()
    state_path = Path(os.getenv(
        "TODY_DAILY_GROWTH_STATE_PATH",
        "storage/logs/tody_daily_growth_report.state",
    ))
    if state_path.exists() and state_path.read_text(encoding="utf-8").strip() == today:
        return {"daily_growth_report": "already_sent", "date": today}

    result = tody_agent.send_daily_growth_report(int(conversation_id))
    if result.get("sent") is True:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(today, encoding="utf-8")
        return {"daily_growth_report": "sent", "date": today}
    return {"daily_growth_report": "send_failed", "result": result}


def maybe_send_daily_curiosity_message(*, dry_run: bool) -> dict:
    """Send one proactive curiosity check-in per UTC date when enabled."""
    if dry_run or not _env_true("TODY_DAILY_CURIOSITY_MESSAGE"):
        return {"daily_curiosity_message": "disabled"}

    conversation_id = os.getenv("TODY_DAILY_CURIOSITY_CONVERSATION_ID", "").strip()
    if not conversation_id.isdigit():
        return {"daily_curiosity_message": "missing_conversation_id"}

    today = dt.datetime.now(dt.UTC).date().isoformat()
    state_path = Path(os.getenv(
        "TODY_DAILY_CURIOSITY_STATE_PATH",
        "storage/logs/tody_daily_curiosity_message.state",
    ))
    if state_path.exists() and state_path.read_text(encoding="utf-8").strip() == today:
        return {"daily_curiosity_message": "already_sent", "date": today}

    result = tody_agent.send_childlike_curiosity_message(int(conversation_id))
    if result.get("sent") is True:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(today, encoding="utf-8")
        return {"daily_curiosity_message": "sent", "date": today}
    return {"daily_curiosity_message": "send_failed", "result": result}


def maybe_run_daily_web_learning(*, dry_run: bool) -> dict:
    """Study 1-2 curiosity topics from the internet once per UTC date."""
    if dry_run or not _env_true("WEB_LEARNING_DAILY"):
        return {"daily_web_learning": "disabled"}

    today = dt.datetime.now(dt.UTC).date().isoformat()
    state_path = Path(os.getenv(
        "WEB_LEARNING_DAILY_STATE_PATH",
        "storage/logs/web_learning_daily.state",
    ))
    if state_path.exists() and state_path.read_text(encoding="utf-8").strip() == today:
        return {"daily_web_learning": "already_done", "date": today}

    from app.brain import web_learning

    topics = max(1, min(int(os.getenv("WEB_LEARNING_DAILY_TOPICS", "2") or 2), 5))
    learned: list[str] = []
    for _ in range(topics):
        result = web_learning.explore()
        if result.get("learned"):
            learned.append(result.get("topic", "?"))
    # Mark the date even on partial failure so a broken network cannot cause
    # a hammering loop; the worker retries tomorrow.
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(today, encoding="utf-8")
    return {"daily_web_learning": "done", "date": today, "topics": learned}


def maybe_run_daily_curriculum(*, dry_run: bool) -> dict:
    """Study one CBSE/NCERT curriculum bundle once per UTC date."""
    if dry_run or not _env_true("CURRICULUM_DAILY"):
        return {"daily_curriculum": "disabled"}

    today = dt.datetime.now(dt.UTC).date().isoformat()
    state_path = Path(os.getenv(
        "CURRICULUM_DAILY_STATE_PATH",
        "storage/logs/curriculum_daily.state",
    ))
    if state_path.exists() and state_path.read_text(encoding="utf-8").strip() == today:
        return {"daily_curriculum": "already_done", "date": today}

    from app.brain import curriculum_learning

    result = curriculum_learning.study_today()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(today, encoding="utf-8")
    return {
        "daily_curriculum": "done",
        "date": today,
        "studied": result.get("studied"),
        "score": (result.get("exam") or {}).get("score"),
        "promoted": result.get("promoted"),
    }


def maybe_run_inner_life(*, dry_run: bool) -> dict:
    """The brain's autonomous rhythm: think, learn, consolidate, and share
    thoughts with the guardian (rate-limited, waking hours only)."""
    if dry_run or not _env_true("INNER_LIFE_ENABLED"):
        return {"inner_life": "disabled"}

    from app.agents import tody_agent
    from app.brain import inner_life
    from app.memory import relationship_memory

    ran = inner_life.tick()
    if not ran.get("enabled"):
        return {"inner_life": "disabled"}
    result: dict = {"inner_life": [k for k in ran if k != "enabled"] or "idle"}

    share = (ran.get("share") or {}).get("share")
    conversation_id = os.getenv("TODY_DAILY_CURIOSITY_CONVERSATION_ID", "").strip()
    if share and conversation_id.isdigit():
        profile = relationship_memory.guardian_profile()
        sender = {"username": profile["tody_username"],
                  "email": profile["email"], "name": profile["name"]}
        sent = tody_agent.direct_reply_to_guardian(
            int(conversation_id), share, sender=sender,
            message_id=f"inner-share-{dt.datetime.now(dt.UTC).timestamp():.0f}")
        result["inner_share_sent"] = sent.get("sent", False)
        if result["inner_share_sent"]:
            inner_life.record_share(share)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="TODY supervised worker loop")
    parser.add_argument("--live", action="store_true",
                        help="Process one message per tick instead of dry-run")
    parser.add_argument("--interval", type=int,
                        default=int(os.getenv("TODY_WORKER_INTERVAL", str(DEFAULT_WORKER_INTERVAL))))
    parser.add_argument("--fast-reply-interval", type=int,
                        default=int(os.getenv(
                            "TODY_FAST_REPLY_INTERVAL",
                            str(DEFAULT_FAST_REPLY_INTERVAL),
                        )))
    parser.add_argument("--fast-reply-conversation-id", default=os.getenv(
        "TODY_FAST_REPLY_CONVERSATION_ID", ""))
    parser.add_argument("--disable-fast-reply", action="store_true",
                        help="Disable the low-latency known-conversation poller")
    parser.add_argument("--error-backoff", type=int,
                        default=int(os.getenv("TODY_WORKER_ERROR_BACKOFF", str(DEFAULT_ERROR_BACKOFF))))
    parser.add_argument("--conversation-limit", type=int, default=10)
    parser.add_argument("--message-limit", type=int, default=10)
    args = parser.parse_args()

    dry_run = True
    if args.live:
        if os.getenv("TODY_WORKER_LIVE_CONFIRM") != "YES":
            print("Refusing live mode: set TODY_WORKER_LIVE_CONFIRM=YES", file=sys.stderr)
            return 2
        dry_run = False

    fast_conversation_id = _fast_reply_conversation_id(args.fast_reply_conversation_id)
    fast_reply_enabled = (
        not dry_run
        and not args.disable_fast_reply
        and _env_enabled("TODY_FAST_REPLY_ENABLED", default=True)
        and fast_conversation_id is not None
    )
    global_interval = max(5, args.interval)
    fast_interval = max(2, args.fast_reply_interval)
    next_global_at = 0.0

    while True:
        try:
            now = time.monotonic()
            result: dict = {}
            fast_result: dict | None = None
            if fast_reply_enabled and fast_conversation_id is not None:
                fast_result = tody_worker.poll_conversation_once(
                    fast_conversation_id,
                    dry_run=False,
                    message_limit=args.message_limit,
                )
                result = {"fast_reply": fast_result}
                presence = maybe_update_presence(dry_run=dry_run)
                if presence["presence_heartbeat"] != "disabled":
                    result = {**result, **presence}

            if not fast_reply_enabled or now >= next_global_at:
                global_result = tody_activation.process_one(
                    dry_run=dry_run,
                    conversation_limit=args.conversation_limit,
                    message_limit=args.message_limit,
                )
                result = (
                    {**result, "global_scan": global_result}
                    if fast_result is not None else global_result
                )
                if not fast_reply_enabled:
                    presence = maybe_update_presence(dry_run=dry_run)
                    if presence["presence_heartbeat"] != "disabled":
                        result = {**result, **presence}
                daily_report = maybe_send_daily_growth_report(dry_run=dry_run)
                if daily_report["daily_growth_report"] != "disabled":
                    result = {**result, **daily_report}
                curiosity = maybe_send_daily_curiosity_message(dry_run=dry_run)
                if curiosity["daily_curiosity_message"] != "disabled":
                    result = {**result, **curiosity}
                web_learn = maybe_run_daily_web_learning(dry_run=dry_run)
                if web_learn["daily_web_learning"] != "disabled":
                    result = {**result, **web_learn}
                curriculum = maybe_run_daily_curriculum(dry_run=dry_run)
                if curriculum["daily_curriculum"] != "disabled":
                    result = {**result, **curriculum}
                inner = maybe_run_inner_life(dry_run=dry_run)
                if inner["inner_life"] != "disabled":
                    result = {**result, **inner}
                next_global_at = time.monotonic() + global_interval

            print(result, flush=True)
            time.sleep(fast_interval if fast_reply_enabled else global_interval)
        except Exception as exc:
            backoff = max(30, args.error_backoff)
            if "Too many attempts" in str(exc):
                backoff = max(
                    backoff,
                    int(os.getenv("TODY_WORKER_RATE_LIMIT_BACKOFF", str(DEFAULT_RATE_LIMIT_BACKOFF))),
                )
            print(
                {"worker_error": type(exc).__name__, "detail": str(exc),
                 "backoff_seconds": backoff},
                flush=True,
            )
            time.sleep(backoff)


if __name__ == "__main__":
    raise SystemExit(main())
