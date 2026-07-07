"""Proactive initiative + curiosity closure — Shree acts on her own, not just
reacts.

Two AGI gaps from the rohitsingh chat log:
  B. No proactive initiative. Every advance was Rohit prompting. She never said
     "Papa, I noticed the fee test failed — want me to look?" She has inner_life
     but its shares are one-way broadcasts, not the result of noticing something
     in her world and deciding it matters.
  E. No curiosity closure. When she couldn't answer ("gold price offline",
     turn 1733), she dropped it. An AGI queues it, researches it when the
     LLM/web is back, and proactively tells Papa the answer.

This module is the unified proactive layer:
  - observe()        → scan for things worth acting on (open promises from
                       thread_state, queued curiosity questions, recent audit
                       failures) and pick ONE.
  - act_on(item)     → draft a proactive message and queue it through the
                       normal approval-gated send (never auto-sends — HIGH tier
                       stays gated per Rohit's choice).
  - run_cycle()      → observe + act_on the top item, once. The worker calls
                       this on a slow interval (e.g. every 30 min).

State (the curiosity queue) is persisted to a JSON file so it survives restarts.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

from app.agents import tody_agent
from app.brain import thread_state
from app.config import get_settings
from app.integrations.tody_client import TodyError
from app.memory import dialogue_memory
from app.safety.audit_logger import log_event_safe

_QUEUE_PATH = Path("storage/logs/curiosity_queue.json")
_GUARDIAN_CONV_KEY = "guardian_conversation_id"  # resolved lazily from settings


def _queue_path() -> Path:
    return _QUEUE_PATH


def _load_queue() -> dict:
    try:
        return json.loads(_queue_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"pending": [], "done": []}


def _save_queue(data: dict) -> None:
    try:
        _queue_path().parent.mkdir(parents=True, exist_ok=True)
        _queue_path().write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def queue_question(question: str, *, source: str = "chat") -> None:
    """Add an unanswered question to the curiosity queue (Phase E). Called when
    Shree can't answer something and wants to close the loop later."""
    q = (question or "").strip()
    if not q:
        return
    data = _load_queue()
    # dedup
    if any(p["question"].lower() == q.lower() for p in data["pending"]):
        return
    data["pending"].append({"question": q, "source": source,
                            "queued_at": dt.datetime.now(dt.UTC).isoformat()})
    _save_queue(data)
    log_event_safe("curiosity_queued", detail=f"q={q[:80]}; source={source}",
                   risk_tier="low", actor="shree")


def _mark_done(item: dict, answer: str) -> None:
    data = _load_queue()
    data["pending"] = [p for p in data["pending"]
                       if p["question"] != item["question"]]
    data["done"].append({**item, "answer": answer[:400],
                         "closed_at": dt.datetime.now(dt.UTC).isoformat()})
    data["done"] = data["done"][-50:]  # cap history
    _save_queue(data)


@dataclass
class Initiative:
    kind: str            # promise | curiosity | audit_failure
    conversation_id: int | None
    text: str            # what to say to Papa
    payload: dict


def _guardian_conversation_id() -> int | None:
    """The fast-reply guardian conversation id from settings, if configured."""
    cid = (get_settings().tody_fast_reply_conversation_id or "").strip()
    try:
        return int(cid) if cid else None
    except ValueError:
        return None


def _observe_promises() -> Initiative | None:
    """Open promises Shree made to the guardian — does any have a closure now?"""
    cid = _guardian_conversation_id()
    if cid is None:
        return None
    promises = thread_state.open_promises(cid)
    if not promises:
        return None
    p = promises[0]
    return Initiative("promise", cid,
                      f"Papa, you'd asked me to follow up on this — "
                      f"\"{p['text'][:80]}\". Status check: I haven't seen it "
                      "happen yet; want me to keep watching?",
                      {"promise": p})


def _observe_curiosity() -> Initiative | None:
    """The oldest queued curiosity question — try to answer it now (web/LLM)."""
    data = _load_queue()
    if not data["pending"]:
        return None
    item = data["pending"][0]
    # Attempt to answer it now via the chat tool-loop's web_lookup.
    try:
        from app.agents import chat_tool_loop
        if chat_tool_loop.should_run_tool_loop(item["question"]):
            loop = chat_tool_loop.run(
                f"Answer this question factually: {item['question']}")
            if loop.reply and not loop.error:
                _mark_done(item, loop.reply)
                return Initiative("curiosity", _guardian_conversation_id(),
                                  f"Papa, you'd asked earlier: "
                                  f"\"{item['question'][:80]}\". Here's what I "
                                  f"found: {loop.reply[:300]}",
                                  {"question": item["question"],
                                   "answer": loop.reply})
    except Exception:  # noqa: BLE001
        pass
    return None


def _observe_audit_failures() -> Initiative | None:
    """Recent reply_quality_failure / coding failures → offer to help."""
    try:
        from sqlalchemy import desc, select
        from app.db.models import CognitiveAuditLog, session_scope
        cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(hours=6)
        with session_scope() as s:
            rows = s.scalars(
                select(CognitiveAuditLog).where(
                    CognitiveAuditLog.action.in_(
                        ("reply_quality_failure", "coding_action_blocked"))
                ).order_by(desc(CognitiveAuditLog.id)).limit(5)
            ).all()
            recent = [r for r in rows if r.created_at and r.created_at >= cutoff]
        if not recent:
            return None
        r = recent[0]
        return Initiative("audit_failure", _guardian_conversation_id(),
                          f"Papa, I noticed a {r.action} in the last few hours "
                          f"({(r.detail or '')[:80]}). Want me to look into it?",
                          {"action": r.action, "detail": r.detail})
    except Exception:  # noqa: BLE001
        return None


def observe() -> Initiative | None:
    """Pick ONE thing worth proactively telling Papa about, in priority order:
    a closable curiosity question > an open promise > a recent failure."""
    for fn in (_observe_curiosity, _observe_promises, _observe_audit_failures):
        try:
            item = fn()
        except Exception:  # noqa: BLE001
            item = None
        if item is not None:
            return item
    return None


def act_on(initiative: Initiative) -> dict:
    """Draft a proactive message and queue it through the approval-gated send.
    NEVER auto-sends — per Rohit's choice, proactive sends stay approval-gated."""
    if initiative.conversation_id is None:
        return {"proposed": False,
                "reason": "no guardian conversation configured for proactive sends"}
    try:
        queued = tody_agent.request_send(int(initiative.conversation_id),
                                         initiative.text)
        log_event_safe("proactive_initiative",
                       detail=f"kind={initiative.kind}; conv={initiative.conversation_id}; "
                              f"text={initiative.text[:60]}",
                       risk_tier="high", actor="shree")
        return {"proposed": True, "kind": initiative.kind,
                "conversation_id": initiative.conversation_id,
                "draft": initiative.text, "queued": queued}
    except TodyError as exc:
        return {"proposed": False, "reason": f"tody error: {exc}"}


def run_cycle() -> dict:
    """One proactive cycle: observe → act_on the top item. The worker calls
    this on a slow interval. Returns what it did (or that there was nothing)."""
    initiative = observe()
    if initiative is None:
        return {"proposed": False, "reason": "nothing to act on right now"}
    return act_on(initiative)
