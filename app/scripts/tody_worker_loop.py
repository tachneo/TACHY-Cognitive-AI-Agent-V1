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


def _env_true(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


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
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="TODY supervised worker loop")
    parser.add_argument("--live", action="store_true",
                        help="Process one message per tick instead of dry-run")
    parser.add_argument("--interval", type=int,
                        default=int(os.getenv("TODY_WORKER_INTERVAL", "20")))
    parser.add_argument("--error-backoff", type=int,
                        default=int(os.getenv("TODY_WORKER_ERROR_BACKOFF", "300")))
    parser.add_argument("--conversation-limit", type=int, default=10)
    parser.add_argument("--message-limit", type=int, default=10)
    args = parser.parse_args()

    dry_run = True
    if args.live:
        if os.getenv("TODY_WORKER_LIVE_CONFIRM") != "YES":
            print("Refusing live mode: set TODY_WORKER_LIVE_CONFIRM=YES", file=sys.stderr)
            return 2
        dry_run = False

    while True:
        try:
            result = tody_activation.process_one(
                dry_run=dry_run,
                conversation_limit=args.conversation_limit,
                message_limit=args.message_limit,
            )
            daily_report = maybe_send_daily_growth_report(dry_run=dry_run)
            if daily_report["daily_growth_report"] != "disabled":
                result = {**result, **daily_report}
            curiosity = maybe_send_daily_curiosity_message(dry_run=dry_run)
            if curiosity["daily_curiosity_message"] != "disabled":
                result = {**result, **curiosity}
            web_learn = maybe_run_daily_web_learning(dry_run=dry_run)
            if web_learn["daily_web_learning"] != "disabled":
                result = {**result, **web_learn}
            inner = maybe_run_inner_life(dry_run=dry_run)
            if inner["inner_life"] != "disabled":
                result = {**result, **inner}
            print(result, flush=True)
            time.sleep(max(5, args.interval))
        except Exception as exc:
            print(
                {"worker_error": type(exc).__name__, "detail": str(exc),
                 "backoff_seconds": max(30, args.error_backoff)},
                flush=True,
            )
            time.sleep(max(30, args.error_backoff))


if __name__ == "__main__":
    raise SystemExit(main())
