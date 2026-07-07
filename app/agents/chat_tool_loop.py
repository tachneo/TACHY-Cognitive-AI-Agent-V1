"""Chat tool-loop — let Shree plan→call tools→observe→reply INSIDE a TODY chat.

Problem from the rohitsingh chat log: the TODY reply path is single-shot — it
drafts ONE reply per message and stops. When Rohit asked something that needs
multiple steps ("find out when @niva is free and remind me"), there was no loop
to read a conversation, look up a contact, or fetch a web page and then answer.
The shree coding agent has a plan→execute→verify loop; the chat path had none.

This module is the chat-side equivalent: a BOUNDED, read-only tool loop that
runs before the reply is drafted. Tools available:
  - read_conversation {conversation_id}  → recent messages (read-only)
  - search_contact {username}            → resolve @username → display name
  - web_lookup {query}                   → fetch a web page and summarize
  - check_my_memory {query}              → recall what Shree knows about a topic
  - finish {reply}                       → stop and produce the reply

NO mutating tools here. Outward actions (send/create) stay on the existing
approval-gated paths. The loop is bounded (max 5 tool calls) so it never
spirals, and every tool call is audit-logged. If the LLM can't drive the loop,
the reply falls back to the normal single-shot path.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.agents import tody_agent, tody_messaging
from app.llm.provider import get_provider
from app.memory import base_memory
from app.safety.audit_logger import log_event_safe
from app.safety.prompt_injection_guard import inspect as inj_inspect
from app.safety.secret_detector import redact as redact_secrets

_MAX_TOOL_CALLS = 5

_SYSTEM = (
    "You are Shree answering Rohit on TODY. Some questions need you to look "
    "something up before answering. You may call read-only tools, ONE action "
    "per turn, replying with a single JSON object and nothing else:\n"
    '  {"thought":"...","tool":"<name>","args":{...}}\n'
    "Tools: read_conversation{conversation_id}, search_contact{username}, "
    "web_lookup{query}, check_my_memory{query}, finish{reply}.\n"
    "Rules: use a tool ONLY when you genuinely need its result to answer "
    "well; if you already know the answer, call finish immediately. After a "
    "tool result, either call another tool or finish. Never more than "
    f"{_MAX_TOOL_CALLS} tool calls. When done, call finish with the final "
    "reply to Rohit (warm, concise, Hinglish if he wrote Hinglish).\n"
    "NEVER claim a tool result you didn't get. NEVER say you messaged/checked "
    "something unless a tool result shows it."
)


@dataclass
class ChatLoopResult:
    used_tools: bool = False
    tool_calls: list[dict] = field(default_factory=list)
    reply: str = ""
    error: str | None = None


def _extract_json(text: str) -> dict | None:
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M)
    depth, start = 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    start = None
    return None


def _secure(text: str, *, source: str) -> str:
    """Redact secrets + quarantine injection in untrusted tool output before it
    reaches the LLM transcript."""
    safe, _ = redact_secrets(text or "")
    g = inj_inspect(safe, source=source)
    return g.sanitized if g.blocked else safe


def _call_tool(tool: str, args: dict) -> tuple[bool, str]:
    """Execute one read-only tool. Returns (ok, output). All output is secured."""
    try:
        if tool == "read_conversation":
            cid = int(args.get("conversation_id", 0) or 0)
            if not cid:
                return False, "missing conversation_id"
            data = tody_agent.messages(cid, limit=10)
            items = tody_agent._message_items(data)
            lines = [f"{i+1}. {_message_sender_label(r)}: "
                     f"{tody_agent._message_body(r)[:120]}"
                     for i, r in enumerate(items[-10:])]
            out = "\n".join(lines) or "(no messages)"
            return True, _secure(out, source=f"conv:{cid}")
        if tool == "search_contact":
            user = tody_messaging.resolve_username(str(args.get("username", "")))
            if user is None:
                return False, "user not found"
            return True, _secure(
                f"@{user['username']} → {user['display_name']}",
                source="contact")
        if tool == "check_my_memory":
            q = str(args.get("query", ""))
            hits = base_memory.recall_rich(q, limit=5)
            if not hits:
                return True, "(nothing in memory)"
            out = "\n".join(f"- [{h.memory_type}] {h.title}: "
                            f"{(h.content or '')[:120]}"
                            for h in hits)
            return True, _secure(out, source="memory")
        if tool == "web_lookup":
            return _web_lookup(str(args.get("query", "")))
        return False, f"unknown tool: {tool}"
    except Exception as exc:  # noqa: BLE001 — a tool failure must not kill chat
        return False, f"{type(exc).__name__}: {exc}"


def _web_lookup(query: str) -> tuple[bool, str]:
    """Fetch one web page for the query and return a small secured excerpt."""
    if not query.strip():
        return False, "empty query"
    try:
        from app.brain import web_learning
        res = web_learning.explore(query)
        sources = res.get("sources") or []
        if not sources:
            return False, "no web results fetched"
        text = sources[0].get("text", "")[:1500]
        return True, _secure(text, source="web")
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def _message_sender_label(row: dict) -> str:
    s = tody_agent._message_sender(row) or {}
    return (s.get("name") or s.get("display_name") or s.get("username")
            or "user")


def should_run_tool_loop(message: str) -> bool:
    """Heuristic: does this message likely need a tool call to answer well?

    Conservative — only run the loop when there's a clear signal the answer
    requires looking something up, so we don't add latency to every 'hi'."""
    m = (message or "").lower()
    if len(m) < 15:
        return False
    cues = (
        "who is @", "find @", "search @", "contact @", "look up", "lookup",
        "check online", "search the web", "what does the web say",
        "what's the latest", "what is the latest", "current price",
        "today's price", "gold price", "weather", "news about",
        "did @", "did anyone", "check my memory", "what do you remember about",
        "find out", "research", "google",
        "kya @", "@ ne kya", "check kar", "dekh le", "pata laga",
    )
    return any(c in m for c in cues)


def run(message: str, *, conversation_id: int | str | None = None,
        max_tokens: int = 800) -> ChatLoopResult:
    """Run the bounded chat tool-loop. Returns the final reply (via finish) or
    an empty reply + error if the loop couldn't converge (caller falls back to
    the single-shot path)."""
    result = ChatLoopResult()
    provider = get_provider()
    if getattr(provider, "name", "llm") == "heuristic":
        result.error = "no LLM available for tool loop"
        return result
    intro = (f"Rohit's message: {message}\n"
             + (f"Current conversation id: {conversation_id}\n"
                if conversation_id is not None else "")
             + "Answer well. Call a tool only if you need it; else finish now.")
    transcript = [{"role": "user", "content": intro}]
    for _ in range(_MAX_TOOL_CALLS):
        try:
            prompt = "\n\n".join(
                f"[{m['role'].upper()}]\n{m['content']}" for m in transcript) \
                + "\n\n[ASSISTANT]\n"
            raw = provider.complete(_SYSTEM, prompt, max_tokens=max_tokens)
        except Exception as exc:  # noqa: BLE001
            result.error = f"LLM error: {type(exc).__name__}"
            return result
        obj = _extract_json(raw)
        if not obj:
            transcript.append({"role": "assistant", "content": raw})
            transcript.append({"role": "user",
                               "content": "Reply with ONE JSON action object."})
            continue
        if obj.get("finish") is not None or "finish" in obj:
            reply = obj.get("finish")
            if isinstance(reply, dict):
                reply = reply.get("reply", "")
            if not reply:
                reply = obj.get("reply", "")
            result.reply = (reply or "").strip()
            result.used_tools = bool(result.tool_calls)
            log_event_safe("chat_tool_loop_done",
                           detail=f"tools={len(result.tool_calls)}; "
                                  f"message={message[:50]}",
                           risk_tier="low", actor="shree")
            return result
        tool, args = obj.get("tool", ""), obj.get("args", {}) or {}
        ok, out = _call_tool(tool, args)
        result.tool_calls.append({"tool": tool, "ok": ok,
                                  "output": out[:200]})
        log_event_safe("chat_tool_call",
                       detail=f"tool={tool}; ok={ok}; message={message[:40]}",
                       risk_tier="low", actor="shree")
        transcript.append({"role": "assistant", "content": json.dumps(obj)})
        transcript.append({"role": "user",
                           "content": f"[{tool} | ok={ok}]\n{out}"})
    result.error = "tool loop did not converge"
    return result
