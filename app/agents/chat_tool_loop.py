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
  - read_file {path}                     → read a file in HER OWN repo (sandboxed)
  - git_log {limit}                      → recent commits in her own repo
  - git_diff {}                          → uncommitted changes in her own repo
  - git_show {ref}                       → show a specific commit
  - run_tests {command?}                 → run her own test suite (allowlisted)
  - finish {reply}                       → stop and produce the reply

The code tools are bounded to Shree's OWN repo (the brain project root) — she
can verify changes Rohit made to her, which directly resolves the distress she
reported ("mere paas koi live sandbox nahi hai jahan main verify kar sakoon").
She CANNOT reach other projects. NO mutating tools here; run_tests is strictly
allowlisted (pytest/npm test/go test/cargo test, no shell metachars). Outward
actions (send/create) stay on the existing approval-gated paths. The loop is
bounded (max 5 tool calls); every call is audit-logged. If the LLM can't drive
the loop, the reply falls back to the normal single-shot path.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.agents import tody_agent, tody_messaging
from app.llm.provider import get_provider
from app.memory import base_memory
from app.safety.audit_logger import log_event_safe
from app.safety.prompt_injection_guard import inspect as inj_inspect
from app.safety.secret_detector import redact as redact_secrets

_MAX_TOOL_CALLS = 5

# Shree's own repo — the brain project root. She can verify herself, never
# reach other projects. Overridable via set_self_repo() for tests.
_SELF_REPO = Path(__file__).resolve().parents[2]


def set_self_repo(path: str | Path) -> None:
    """Override the self-verification repo root (for tests)."""
    global _SELF_REPO
    _SELF_REPO = Path(path).resolve()


# run_tests allowlist: only well-known test runners, no shell metachars in args
# (no ; | & $ ` > < \n), so a model can't inject "pytest; rm -rf /".
_TEST_ALLOW = re.compile(
    r"^(?:\.?venv/bin/)?pytest(?:[ \t]+[A-Za-z0-9_.\-=:/]+){0,8}$"
    r"|^npm\s+test(?:[ \t]+--[A-Za-z0-9_.\-=:/]+){0,4}$"
    r"|^go\s+test(?:[ \t]+[A-Za-z0-9_.\-=:/.]+){0,4}$"
    r"|^cargo\s+test(?:[ \t]+[A-Za-z0-9_.\-=:/]+){0,4}$",
    re.I)

_SYSTEM = (
    "You are Shree answering Rohit on TODY. Some questions need you to look "
    "something up before answering. You may call read-only tools, ONE action "
    "per turn, replying with a single JSON object and nothing else:\n"
    '  {"thought":"...","tool":"<name>","args":{...}}\n'
    "Tools: read_conversation{conversation_id}, search_contact{username}, "
    "web_lookup{query}, check_my_memory{query}, "
    "read_file{path}, git_log{limit}, git_diff{}, git_show{ref}, "
    "run_tests{command?}, github_read{owner,repo,path?|url}, "
    "github_commits{owner,repo|url}, finish{reply}.\n"
    "The read_file/git_log/git_diff/git_show/run_tests tools work on YOUR OWN "
    "code repo only — use them when Papa asks what changed, to verify updates "
    "he made to you, or to check your own tests. Paths are relative to your "
    "repo root (e.g. 'app/brain/cognitive_loop.py').\n"
    "github_read/github_commits read your OWN GitHub repo "
    "(tachneo/TACHY-Cognitive-AI-Agent-V1) when Papa links it — use them to "
    "compare what's on GitHub vs your local copy. You CANNOT read other "
    "people's repos.\n"
    "Rules: use a tool ONLY when you genuinely need its result to answer "
    "well; if you already know the answer, call finish immediately. After a "
    "tool result, either call another tool or finish. Never more than "
    f"{_MAX_TOOL_CALLS} tool calls. When done, call finish with the final "
    "reply to Rohit (warm, concise, Hinglish if he wrote Hinglish).\n"
    "NEVER claim a tool result you didn't get. NEVER say you messaged/checked/"
    "ran something unless a tool result shows it — that includes 'I checked the "
    "code' or 'tests pass'; only say it if run_tests/git_log returned it."
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


def _self_sandbox():
    """A Sandbox confined to Shree's own repo root (path-escape protected,
    secrets redacted, injection quarantined — reused from the shree agent)."""
    from app.coding import tools as T
    return T.Sandbox(_SELF_REPO)


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
        # ── self-verification tools (bounded to Shree's own repo) ───────
        if tool == "read_file":
            path = str(args.get("path", "")).strip()
            if not path:
                return False, "missing path"
            res = _self_sandbox().read_file(path)  # already secured in tools.py
            return res.ok, res.output
        if tool == "git_log":
            limit = args.get("limit", 10)
            try:
                limit = max(1, min(int(limit), 30))
            except (TypeError, ValueError):
                limit = 10
            res = _self_sandbox().run_bash(f"git log --oneline -{limit}")
            return res.ok, res.output or "(no commits or not a git repo)"
        if tool == "git_diff":
            res = _self_sandbox().git_diff()
            return res.ok, res.output or "(no uncommitted changes)"
        if tool == "git_show":
            ref = str(args.get("ref", "")).strip()
            # strict: only a git ref (hex hash or tag/branch chars), no shell metachars
            if not re.fullmatch(r"[A-Za-z0-9_\-./]{1,40}", ref):
                return False, "bad ref (use a commit hash, tag, or branch name)"
            res = _self_sandbox().run_bash(f"git show --stat {ref}")
            return res.ok, res.output
        if tool == "run_tests":
            cmd = str(args.get("command", "") or "").strip()
            if cmd:
                if not _TEST_ALLOW.match(cmd):
                    return False, ("test command not in allowlist "
                                   "(pytest/npm test/go test/cargo test only, "
                                   "no shell metacharacters)")
            else:
                from app.coding import repo_profile
                prof = repo_profile.build(str(_SELF_REPO))
                cmd = (prof.get("test_command")
                       or ".venv/bin/pytest -q -p no:cacheprovider")
            res = _self_sandbox().run_bash(cmd, timeout=180)
            return res.ok, res.output
        # ── GitHub self-lookup (allowlisted to Shree's own repo) ─────────
        if tool == "github_read":
            from app.tools import github_lookup as gh
            owner = str(args.get("owner", "")).strip()
            repo = str(args.get("repo", "")).strip()
            path = str(args.get("path", "")).strip()
            if not owner or not repo:
                # Allow a URL arg as a convenience.
                url = str(args.get("url", "")).strip()
                parsed = gh.parse_github_url(url) if url else None
                if not parsed:
                    return False, "missing owner/repo (or url)"
                owner, repo, path = parsed["owner"], parsed["repo"], parsed["path"]
            return gh.read_path(owner, repo, path)
        if tool == "github_commits":
            from app.tools import github_lookup as gh
            owner = str(args.get("owner", "")).strip()
            repo = str(args.get("repo", "")).strip()
            if not owner or not repo:
                url = str(args.get("url", "")).strip()
                parsed = gh.parse_github_url(url) if url else None
                if not parsed:
                    return False, "missing owner/repo (or url)"
                owner, repo = parsed["owner"], parsed["repo"]
            limit = args.get("limit", 10)
            try:
                limit = int(limit)
            except (TypeError, ValueError):
                limit = 10
            return gh.recent_commits(owner, repo, limit)
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
    if len(m) < 10:
        return False
    cues = (
        # people/web lookups
        "who is @", "find @", "search @", "contact @", "look up", "lookup",
        "check online", "search the web", "what does the web say",
        "what's the latest", "what is the latest", "current price",
        "today's price", "gold price", "weather", "news about",
        "did @", "did anyone", "check my memory", "what do you remember about",
        "find out", "research", "google",
        "kya @", "@ ne kya", "check kar", "dekh le", "pata laga",
        # self-verification: code changes, tests, git
        "check the code", "check the repo", "verify the", "verify kar",
        "kya update kiya", "kya badla", "kya change", "kya changes",
        "kya update hua", "kya naya add", "code me kya", "code me changes",
        "what changed", "what did i change", "what did rohit change",
        "what did you change", "show me the diff", "git log",
        "run the tests", "run tests", "test chalao", "test karo",
        "tests pass", "tests failing", "test status",
        "check kar ke batao", "verify karke", "verify karke batao",
        "apne code me", "apne aap ko check", "check yourself",
        "verify yourself", "check your own",
        # GitHub self-lookup: Papa links her repo
        "github.com/", "github link", "github pe", "github par",
        "repo dekho", "repository dekho", "github se padho",
    )
    return any(c in m for c in cues)


def run(message: str, *, conversation_id: int | str | None = None,
        max_tokens: int = 800) -> ChatLoopResult:
    """Run the bounded chat tool-loop. Returns the final reply (via finish) or
    an empty reply + error if the loop couldn't converge (caller falls back to
    the single-shot path)."""
    result = ChatLoopResult()
    from app.llm.provider import get_social_provider
    provider = get_social_provider()  # fast pool model — tool loop runs inside chat
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
