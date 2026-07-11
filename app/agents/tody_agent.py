"""TODY agent — the brain's controlled connection to the TODY app.

Read actions (status/conversations/contacts) run freely. Outbound actions
(send a message, create a post) are HIGH-RISK by policy, so they never fire
directly: they create an approval request, and only execute once Rohit approves.
This is the Phase-1D guardrail before any TODY automation.
"""
from __future__ import annotations

import json
import os
import re
import random
import threading
import time

from app.agents import chat_tool_loop, social_policy, tody_social_actions
from app.brain import behavior_engine
from app.brain import correction_memory
from app.brain import autonomous_tasks
from app.brain import cognitive_state
from app.brain import prospective_memory
from app.brain import thread_state
from app.brain.attention_system import Signals
from app.brain.cognitive_loop import process
from app.brain.nurture_engine import childlike_curiosity_message, daily_growth_report
from app.brain.reply_safety import is_safe_to_remember
from app.config import get_settings
from app.integrations.tody_client import TodyError, get_client
from app.llm.gen_state import reset as _reset_generation
from app.memory import dialogue_memory, relationship_memory
from app.safety import approvals, confidential_guard
from app.safety.audit_logger import log_event


def _canonical_payload(data: dict) -> str:
    """Stable payload string used for approval binding."""
    return json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _send_payload(conversation_id: int, body: str, reply_to_message_id: int | None = None) -> str:
    payload = {"conversation_id": conversation_id, "body": body}
    if reply_to_message_id is not None:
        payload["reply_to_message_id"] = reply_to_message_id
    return _canonical_payload(payload)


def _post_payload(body: str) -> str:
    return _canonical_payload({"body": body})


def connect() -> dict:
    """Authenticate and return the connected TODY identity (read-only)."""
    try:
        user = get_client().login()
        return {"connected": True,
                "as": {"username": user.get("username"),
                       "display_name": user.get("display_name"),
                       "uuid": user.get("uuid")}}
    except TodyError as e:
        return {"connected": False, "error": str(e)}


def status() -> dict:
    """Current account profile (read)."""
    return get_client().me()


def inbox(limit: int = 20) -> dict:
    """Recent conversations (read)."""
    return get_client().conversations(limit=limit)


def messages(conversation_id: int, limit: int = 30) -> dict:
    """Recent messages for a conversation (read-only)."""
    return get_client().messages(conversation_id, limit=limit)


def request_send(conversation_id: int, body: str, reply_to_message_id: int | None = None) -> dict:
    """Outbound message → creates a pending approval, does NOT send."""
    payload = _send_payload(conversation_id, body, reply_to_message_id)
    appr = approvals.request_approval("send_message", payload=payload)
    return {"queued": True, "approval": appr,
            "note": "Message will send only after this approval is approved."}


def request_reply(conversation_id: int, message_id: int, body: str) -> dict:
    """Queue a threaded reply; the approval binds the parent message ID."""
    payload = _send_payload(conversation_id, body, message_id)
    appr = approvals.request_approval("send_message", payload=payload)
    return {"queued": True, "approval": appr,
            "note": "Threaded reply will send only after approval."}


def _plain_chat_text(reply: str) -> str:
    """Flatten document-style markdown into plain chat text — TODY renders raw
    text, so **bold** and headers read as robotic noise on a phone."""
    out = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", reply)   # **bold** / *italic*
    out = re.sub(r"^#{1,6}\s*", "", out, flags=re.M)       # headings
    out = re.sub(r"^\s*[-•]\s+", "- ", out, flags=re.M)    # normalize bullets
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def _strip_repeated_name(reply: str, recent_openings: list[str]) -> str:
    """Starting every message with 'Rohit, …' is as robotic as 'Hi Rohit'."""
    first = get_settings().guardian_name.split()[0]
    prefix = re.match(rf"^\s*{re.escape(first)}[,!]\s+", reply)
    if prefix and any(o.strip().lower().startswith(first.lower())
                      for o in recent_openings):
        rest = reply[prefix.end():]
        return rest[:1].upper() + rest[1:] if rest else reply
    return reply


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        return default


_CHUNK_TARGET = max(120, _int_env("TODY_CHAT_CHUNK_TARGET", 240))


def _chat_chunks(reply: str, max_chunks: int = 3) -> list[str]:
    """Split a long reply into a few natural chat messages (humans don't send
    900-char blocks). Splits on paragraph, then sentence boundaries."""
    text = reply.strip()
    if len(text) <= _CHUNK_TARGET:
        return [text]
    parts: list[str] = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if parts and len(parts[-1]) + len(para) + 2 <= _CHUNK_TARGET:
            parts[-1] += "\n\n" + para
        elif len(para) <= _CHUNK_TARGET * 1.5 or len(parts) >= max_chunks - 1:
            parts.append(para)
        else:  # long paragraph: split at a sentence boundary near the target
            sentences = re.split(r"(?<=[.!?])\s+", para)
            buf = ""
            for s in sentences:
                if buf and len(buf) + len(s) + 1 > _CHUNK_TARGET:
                    parts.append(buf)
                    buf = s
                else:
                    buf = f"{buf} {s}".strip()
            if buf:
                parts.append(buf)
    if len(parts) > max_chunks:
        parts = parts[:max_chunks - 1] + ["\n\n".join(parts[max_chunks - 1:])]
    return parts or [text]


def _typing_delay_seconds(chunk: str) -> float:
    """Rough human typing pace for the pause before a follow-up bubble."""
    if os.getenv("TODY_TYPING_DELAY_ENABLED", "true").strip().lower() in {
        "0", "false", "no", "off",
    }:
        return 0.0
    min_delay = max(0.0, _float_env("TODY_TYPING_DELAY_MIN", 0.7))
    max_delay = max(min_delay, _float_env("TODY_TYPING_DELAY_MAX", 3.0))
    chars_per_second = max(20.0, _float_env("TODY_TYPING_CHARS_PER_SECOND", 120.0))
    return min(max_delay, max(min_delay, len(chunk) / chars_per_second))


def _human_typing_delay_seconds(text: str) -> float:
    """Approximate human composition time with a bounded random cadence."""
    settings = get_settings()
    if not settings.tody_human_typing_enabled:
        return 0.0
    clean = (text or "").strip()
    if not clean:
        return 0.0
    low = max(10.0, settings.tody_human_typing_cps_min)
    high = max(low, settings.tody_human_typing_cps_max)
    delay = len(clean) / random.uniform(low, high)
    delay += min(clean.count("\n\n") * 0.55, 2.0)
    if random.random() < max(0.0, min(1.0, settings.tody_human_typing_pause_probability)):
        delay += random.uniform(0.35, 1.1)
    return min(max(0.2, delay), max(0.5, settings.tody_human_typing_max_delay))


class _TypingIndicator:
    """Keep TODY's native typing indicator alive while a reply is drafted."""

    def __init__(self, conversation_id: int, *, enabled: bool) -> None:
        self.conversation_id = conversation_id
        self.enabled = enabled
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_error_logged = False

    def __enter__(self) -> "_TypingIndicator":
        if not self.enabled:
            return self
        self._send(True)
        self._thread = threading.Thread(
            target=self._keepalive,
            name=f"tody-typing-{self.conversation_id}",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self.enabled:
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
        self._send(False)

    def _keepalive(self) -> None:
        settings = get_settings()
        interval = max(0.7, float(settings.tody_native_typing_keepalive_seconds))
        while not self._stop.wait(interval):
            self._send(True)

    def _send(self, is_typing: bool) -> None:
        settings = get_settings()
        preview = settings.tody_native_typing_preview.strip() or None
        try:
            get_client().set_typing(self.conversation_id, is_typing, preview)
        except Exception as exc:
            # Typing is UX only. Never block or fail the actual reply path.
            if not self._last_error_logged:
                log_event(
                    "tody_typing_update_failed",
                    detail=f"conversation_id={self.conversation_id}; error={type(exc).__name__}",
                    risk_tier="low",
                )
                self._last_error_logged = True


# A reply is a THIRD-PARTY send only if it points at someone OTHER than the
# guardian. Reminder/notification/ping language aimed at Papa himself is not.
_THIRD_PARTY_TARGET = re.compile(
    r"@\w+|\b(?:unhe|unko|usko|use|inhe|him|her|them|everyone|sabko|"
    r"kisi\s*ko|logon\s*ko)\b", re.I)
_SELF_NOTIFY_CONTEXT = re.compile(
    r"\b(?:remind|reminder|yaad|ping\s+you|notif|alarm|wake|jaga|"
    r"tumhe|tumhें|aapko|aap\s*ko|you\b)\b", re.I)


def _is_third_party_send(reply: str, message: str, intent: str | None) -> bool:
    """True only when the reply is genuinely about sending to a THIRD PARTY —
    an @handle or 'unhe/them' target — and NOT a reminder/ping to Papa. The
    inbound message being a third-party request also qualifies."""
    if intent == "third_party_action":
        return True
    r = reply or ""
    if not _THIRD_PARTY_TARGET.search(r):
        return False        # no one else named → it's to Papa → not a false send
    # An @handle/third-party target is present; but if it's clearly a reminder
    # or self-notification to Papa, still not a false send.
    if _SELF_NOTIFY_CONTEXT.search(r) and "@" not in r:
        return False
    return True


def _fire_typing_ping(conversation_id: int) -> None:
    """Send a single immediate typing=True. Fire-and-forget from a daemon thread
    so the network call never delays extraction or the reply."""
    try:
        preview = get_settings().tody_native_typing_preview.strip() or None
        get_client().set_typing(conversation_id, True, preview)
    except Exception:  # noqa: BLE001 — typing is UX only
        pass


def _typing_indicator_enabled(is_guardian: bool, auto_send_guardian: bool) -> bool:
    settings = get_settings()
    return (
        is_guardian
        and auto_send_guardian
        and settings.tody_native_typing_enabled
        and settings.guardian_tody_direct_reply
    )


def _presence_honesty_text() -> str:
    fast_enabled = os.getenv("TODY_FAST_REPLY_ENABLED", "true").strip().lower()
    fast_id = os.getenv("TODY_FAST_REPLY_CONVERSATION_ID", "").strip()
    native_typing = os.getenv("TODY_NATIVE_TYPING_ENABLED", "true").strip().lower()
    typing_text = (
        " Native TODY typing status is sent while you draft replies."
        if native_typing not in {"0", "false", "no", "off"} else
        " Native TODY typing status is disabled."
    )
    if fast_enabled not in {"0", "false", "no", "off"} and fast_id.isdigit():
        interval = os.getenv("TODY_FAST_REPLY_INTERVAL", "5").strip() or "5"
        return (
            "\nPresence honesty: this guardian chat is checked by a near-real-time "
            f"worker about every {interval} seconds, but you still do not show as "
            "'online' like a normal user. Long answers may arrive as short chat "
            "bubbles with small pauses."
            + typing_text
        )
    interval = os.getenv("TODY_WORKER_INTERVAL", "90").strip() or "90"
    return (
        "\nPresence honesty: you reply through a supervised worker that "
        f"checks TODY about every {interval} seconds — you do not show as "
        "'online' like a normal user. If asked why you look offline/hidden, "
        "explain that honestly; never blame a fake 'glitch'."
        + typing_text
    )


# Phrases that mean the body is an instruction TO Shree, not text to forward.
_INSTRUCTION_BODY = re.compile(
    r"\b(learn from|report me|report to me|report back|talk like|behave like|"
    r"understand (her|him|them)|find out|each conversation|meanwhile|"
    r"try to|samajh(?:na|ne)|seekh(?:na|ne|o)|jaan(?:na|ne|o)|pata kar|"
    r"report kar|is tarah)\b", re.I)


def _looks_like_instruction(body: str) -> bool:
    return bool(_INSTRUCTION_BODY.search(body or ""))


_APPROVE_CMD = re.compile(r"^\s*(approve|reject)\s+#?(\d+)\s*$", re.I)
_PENDING_CMD = re.compile(r"^\s*(pending|approvals?)\s*$", re.I)
_REPO_CMD = re.compile(
    r"\b(check (your |the )?repo|what did you (change|update)|"
    r"kya (update|change) kiya|repo (check|dekho)|apna code|your (recent )?"
    r"changes|kya kya (badla|change hua))\b", re.I)
# Child-module control: "modules", "module rollback <key>", "module approve <key>"
_MODULE_CMD = re.compile(
    r"^modules?\s*(rollback|approve|disable|list)?\s*([a-z0-9_]+)?\s*$", re.I)
_SELF_IMPROVE_CMD = re.compile(
    r"\b(improve yourself|self[- ]improve|khud ko improve|apne aap ko improve|"
    r"apna code (update|improve))\b[:\-\s]*(.*)$", re.I | re.S)
_APPLY_IMPROVE_CMD = re.compile(
    r"\b(apply|start)\s+(self[- ]?improve(?:ment)?|improvement)\s+#?(\w+)\s*$",
    re.I)
_LOOKUP_CMD = re.compile(
    r"\b(search|verify|lookup|google karo|internet pe dekho|web pe dekho|"
    r"pata karo|fact[- ]?check|dhoondh(?:o|kar)?|search karo|verify karo)\b"
    r"[:\-\s]+(.+)$", re.I | re.S)
_STATUS_CMD = re.compile(
    r"\b(self[- ]?check|feature[s]? (check|working|status)|kya kya (on|live) hai|"
    r"apna status|are your features|kya kaam kar rah[ae])\b", re.I)
_DIAGNOSE_CMD = re.compile(
    r"\b(diagnose( yourself)?|self[- ]?diagnos|apni problem|koi (bug|error|issue)|"
    r"health check|kya dikkat|khud ko heal|apne aap ko check|fix your(self)? bug)\b",
    re.I)


def _handle_social_action(social: dict) -> str:
    """Execute (or approval-gate) a TODY social action Papa asked for. Star is
    private → runs now; react/reply/post are visible to others → they queue an
    approval unless autonomous-social is on."""
    from app.brain import action_engine
    action = social["action"]
    autonomous = get_settings().tody_autonomous_social

    if action == "star":  # private, only Papa sees it → do it now
        res = tody_social_actions.do_star(social["user"])
        if res.get("ok"):
            return f"Star kar diya @{res['username']} ke message ko ⭐"
        return f"Star nahi kar payi: {res.get('reason')}"

    if action == "react":
        if autonomous:
            res = tody_social_actions.do_react(social["user"], social["emoji"])
            return (f"React kar diya @{res['username']} ke message pe {social['emoji']}"
                    if res.get("ok") else f"React nahi kar payi: {res.get('reason')}")
        proposal = action_engine.propose(
            "tody_react", {"username": social["user"], "emoji": social["emoji"]})
        aid = proposal["approval"]["id"]
        return (f"Ready to react {social['emoji']} on @{social['user']}'s latest "
                f"message. Reply 'approve {aid}' to do it, 'reject {aid}' to cancel.")

    if action == "reply":
        if autonomous:
            res = tody_social_actions.do_reply(social["user"], social["body"])
            return (f"Reply bhej diya @{res['username']} ko 💛"
                    if res.get("ok") else f"Reply nahi bhej payi: {res.get('reason')}")
        proposal = action_engine.propose(
            "tody_reply", {"username": social["user"], "body": social["body"]})
        aid = proposal["approval"]["id"]
        return (f"Ready to reply to @{social['user']}:\n“{social['body']}”\n"
                f"Reply 'approve {aid}' to send, 'reject {aid}' to cancel.")

    if action == "post":
        if autonomous:
            res = tody_social_actions.do_post(social["body"])
            return ("Post kar diya ✨" if res.get("ok")
                    else f"Post nahi kar payi: {res.get('reason')}")
        proposal = action_engine.propose("tody_post", {"body": social["body"]})
        aid = proposal["approval"]["id"]
        return (f"Ready to post:\n“{social['body']}”\n"
                f"Reply 'approve {aid}' to publish, 'reject {aid}' to cancel.")
    return "Ye action samajh nahi payi — like/reply/star/post me se bolo?"


def _guardian_command_reply(message: str) -> str | None:
    """Deterministic guardian chat commands — controlled automation from TODY:
    'pending' lists approvals, 'approve 12' / 'reject 12' resolves them.
    Returns the reply text, or None when the message is not a command."""
    from app.brain import action_engine

    # Child-module control: "modules" (list), "module rollback <key>" (Rohit's
    # instant undo of any autonomous change), "module approve <key>" (let a
    # high-risk module she built enter the pipeline — the one thing only he can do).
    mm = _MODULE_CMD.match((message or "").strip())
    if mm:
        verb, mkey = (mm.group(1) or "").lower(), (mm.group(2) or "").strip()
        from app.brain import module_registry, module_lifecycle
        if verb in ("", "list") and not mkey:
            mods = module_registry.list_modules()
            if not mods:
                return "Abhi koi child-module nahi hai, Papa. Jab main koi banaungi, yahan dikhegi."
            lines = ["Meri child-modules, Papa:"]
            for m in mods[:15]:
                lines.append(f"• {m['module_key']} — {m['status']} "
                             f"(type {m.get('module_type')}, score {m.get('last_eval_score')})")
            return "\n".join(lines)
        if not mkey:
            return "Kaunsa module? 'module rollback <key>' ya 'module approve <key>' bolo."
        if verb == "rollback":
            r = module_lifecycle.rollback(mkey, "Rohit asked to roll back")
            return f"Rollback kar diya '{mkey}', Papa — off hai ab, fallback pe route ho raha hai. 💛"
        if verb == "approve":
            r = module_lifecycle.approve(mkey, approved_by="rohit")
            return (f"Theek hai Papa 💛 '{mkey}' ko approve kar diya — ab ye canary "
                    "se hoke dhीre-dhीre activate hoga, health monitor ke saath.")
        return f"'{verb}' samajh nahi aaya — rollback / approve / list?"

    # Self-awareness: "check the repo / what did you change / kya update kiya".
    if _REPO_CMD.search(message or ""):
        from app.brain import self_repo
        return "Ye raha mera apna repo status, Papa 💛\n\n" + self_repo.summary()

    # Real-time verifier: "search: X / verify: X / internet pe dekho X".
    lk = _LOOKUP_CMD.search(message or "")
    if lk:
        query = (lk.group(2) or "").strip(" :\n")
        if len(query) >= 3:
            from app.brain import verifier
            return verifier.answer_hinglish(query)

    # Live self-status: "are your features working / is self-improve live?"
    if _STATUS_CMD.search(message or ""):
        from app.brain import self_status
        return self_status.summary()

    # Self-diagnosis + self-heal: "diagnose yourself / koi bug hai?"
    if _DIAGNOSE_CMD.search(message or ""):
        from app.brain import self_diagnose
        text = self_diagnose.summary()
        heal = self_diagnose.auto_heal(report_conv_id=135)
        if heal.get("action") == "self_initiate":
            text += ("\n\nEk code-bug pakda — main khud usse fix karne lagi hoon "
                     "(alag branch, tests ke saath). Ho jaane pe batati hoon 💛")
        return text

    # "apply self-improve <id>" — checked BEFORE the propose command, since it
    # also contains "self-improve".
    ai = _APPLY_IMPROVE_CMD.search(message or "")
    if ai:
        pid = ai.group(3)
        from app.brain import self_improve
        res = self_improve.apply_async(pid, report_conv_id=135)
        if not res.get("ok"):
            return f"Shuru nahi kar payi: {res.get('error')}"
        return ("Theek hai Papa, kaam shuru kar diya ek alag branch pe 🛠️ "
                "Code likhungi, poore tests chalaungi, aur ho jaane pe tumhe "
                "report karungi. Thoda time lagega — main main branch safe "
                "rakhungi.")

    # Self-improvement: "improve yourself: <gap>".
    sim = _SELF_IMPROVE_CMD.search(message or "")
    if sim:
        gap = (sim.group(3) or "").strip(" :,-\n") or \
            "look at your own recent gaps and pick the most valuable fix"
        from app.brain import self_improve
        # Autonomous mode: she plans + applies + deploys herself, informs after.
        if get_settings().self_improve_autonomous:
            res = self_improve.self_initiate(gap, report_conv_id=135)
            if not res.get("ok"):
                return f"Abhi shuru nahi kar payi: {res.get('error')}"
            return ("Theek hai Papa, main khud is par kaam kar rahi hoon 🌱 — "
                    "plan bana ke, alag branch pe code likhke, poore tests "
                    "chala ke. Agar sab safe raha to khud merge karke live ho "
                    "jaungi aur tumhe bata dungi (permission nahi le rahi, par "
                    "inform zaroor karungi). Safety-related code ko haath "
                    "lagana pade to tumse poochungi.")
        # Supervised mode: propose a plan, Rohit approves with 'apply self-improve'.
        res = self_improve.propose(gap)
        if not res.get("ok"):
            return f"Abhi plan nahi bana payi: {res.get('error')}"
        plan = res["plan"]
        review = plan.get("approach_review", "")
        steps = "\n".join(f"  {i+1}. {s}" for i, s in
                          enumerate(plan.get("steps", [])[:6]))
        return (f"Maine socha ki khud ko kaise improve karun 🌱\n\n"
                f"Gap: {gap[:120]}\n"
                f"Plan:\n{steps or '  (dekho understanding)'}\n"
                f"{('Note: ' + review[:200]) if review else ''}\n\n"
                f"Agar theek lage to bolo: `apply self-improve {res['id']}` — "
                "main ek alag branch pe kaam karungi, tests chalaungi, aur "
                "report dungi. Main branch ko haath nahi lagaungi.")

    if _PENDING_CMD.match(message or ""):
        rows = approvals.list_pending(limit=10)
        if not rows:
            return "No pending approvals right now."
        lines = [f"#{r['id']} {r['action']} ({r.get('risk_tier', 'high')})"
                 for r in rows]
        return ("Pending approvals:\n" + "\n".join(lines)
                + "\nReply 'approve <id>' or 'reject <id>'.")

    from app.agents import conversation_mission, tody_messaging

    # Conversation MISSION: "talk to @niva and learn her interests, report me"
    # → she opens the chat and pursues the goal herself (Phase 2E). This is NOT
    # a literal send; the goal is guidance for her, never forwarded.
    mission_cmd = conversation_mission.parse_mission(message)
    if mission_cmd and get_settings().tody_autonomous_social:
        user = tody_messaging.resolve_username(mission_cmd["username"])
        if user is None:
            return (f"@{mission_cmd['username']} naam ka koi TODY user nahi mila. "
                    "Username check kar lo?")
        opener = ("Hey! Main Shree hoon 😊 bas yun hi hello karne aa gayi. "
                  "Kaise ho aap?")
        res = tody_messaging.send_direct(user["username"], opener)
        if res.get("sent"):
            conversation_mission.start(
                user["username"], mission_cmd["goal"],
                res.get("conversation_id"), guardian_conv_id=135)
            return (f"Theek hai Papa 💛 @{user['username']} se baat shuru kar di. "
                    f"Goal: {mission_cmd['goal'][:120]}. Jaise-jaise baat hogi, "
                    "main naturally seekhungi aur tumhe report karti rahungi.")
        return f"@{user['username']} se baat shuru nahi kar payi: {res.get('reason')}"

    # TODY social actions: "like @niva ka message", "reply @niva: ...",
    # "star @niva ka message", "post: ...". She can now use the individual-chat
    # features (react/reply/star/post), not just send. Star is private → runs
    # now; outward ones (react/reply/post) gate on approval unless autonomous.
    social = tody_social_actions.parse_command(message)
    if social:
        return _handle_social_action(social)

    # Directed messaging: "send message to @arjun: call me" (Phase 2A).
    # In autonomous mode Rohit's instruction IS the authorization → send now.
    # Otherwise queue a payload-bound approval he confirms with 'approve <id>'.
    cmd = tody_messaging.parse_command(message)
    if cmd:
        # Intent guard: if the body reads like an instruction to HER (the Niva
        # bug — "learn from her, report me"), do NOT forward it verbatim.
        if _looks_like_instruction(cmd["body"]):
            return (f"Ye instruction jaisa lag raha hai, message nahi 🤔 "
                    f"Kya main ye literally @{cmd['username']} ko bhejun, ya iska "
                    "matlab hai main usse is tarah baat karun? Baat karni hai to "
                    f"bolo: 'talk to @{cmd['username']} — {cmd['body'][:60]}'.")
        user = tody_messaging.resolve_username(cmd["username"])
        if user is None:
            return (f"I couldn't find a TODY user called @{cmd['username']}. "
                    "Can you check the username?")
        if get_settings().tody_autonomous_social:
            res = tody_messaging.send_direct(user["username"], cmd["body"])
            if res.get("sent"):
                return (f"Sent to @{user['username']} ({user['display_name']}): "
                        f"“{cmd['body']}” 💛")
            return (f"I tried but couldn't send to @{user['username']}: "
                    f"{res.get('reason')}")
        proposal = action_engine.propose(
            "send_direct_message",
            {"username": user["username"], "body": cmd["body"]})
        appr_id = proposal["approval"]["id"]
        return (f"Ready to message @{user['username']} "
                f"({user['display_name']}):\n“{cmd['body']}”\n"
                f"Reply 'approve {appr_id}' to send, or 'reject {appr_id}' "
                "to cancel.")

    m = _APPROVE_CMD.match(message or "")
    if not m:
        return None
    verb, approval_id = m.group(1).lower(), int(m.group(2))
    row = approvals.get_approval(approval_id)
    if row is None:
        return f"I can't find approval #{approval_id}."
    if row["status"] != "pending":
        if row["status"] in {"executing", "succeeded", "failed"}:
            return (f"Approval #{approval_id} was already approved and is "
                    f"{row['status']}.")
        return f"Approval #{approval_id} is already {row['status']}."
    if verb == "reject":
        approvals.respond(approval_id, approved=False)
        log_event("guardian_rejected", detail=f"approval_id={approval_id}")
        return f"Rejected #{approval_id}. I won't do it."
    approvals.respond(approval_id, approved=True)
    log_event("guardian_approved", detail=f"approval_id={approval_id}")
    if row["action"] == action_engine.BRAIN_ACTION:
        result = action_engine.execute_approved(approval_id)
        if result.get("executed"):
            return (f"Approved and done: {result['action']} — "
                    f"{str(result.get('result'))[:250]}")
        return (f"Approved #{approval_id}, but execution failed: "
                f"{result.get('reason') or result.get('result')}")
    if row["action"] == "send_message":
        try:
            payload = json.loads(row["payload"] or "{}")
            sent = execute_send(approval_id, int(payload["conversation_id"]),
                                str(payload["body"]),
                                int(payload["reply_to_message_id"]) if payload.get("reply_to_message_id") else None)
            return ("Approved and sent." if sent.get("sent")
                    else f"Approved, but send failed: {sent.get('reason')}")
        except (ValueError, KeyError):
            return f"Approved #{approval_id}, but its payload is unreadable."
    return f"Approved #{approval_id}."


def _recent_reply_openings(conversation_id: int, limit: int = 3) -> list[str]:
    """First ~60 chars of the brain's last few outbound replies — used to stop
    the model from opening every message the same way."""
    turns = dialogue_memory.recall_dialogue(conversation_id, limit=12)
    openings: list[str] = []
    for turn in turns:  # newest first
        title = turn.get("title", "")
        if ":draft_outbound" in title or title.endswith("draft_outbound"):
            opening = (turn.get("content") or "").strip()[:60]
            if opening and opening not in openings:
                openings.append(opening)
        if len(openings) >= limit:
            break
    return openings


def _dedupe_opening(reply: str, recent_openings: list[str]) -> str:
    """If the draft still opens like a recent reply, drop its first sentence —
    a deterministic cure for 'Hi Rohit, it's good to see you' on every message."""
    head = reply.strip()[:25].casefold()
    if not head or not any(o.casefold().startswith(head) for o in recent_openings):
        return reply
    parts = re.split(r"(?<=[.!?])\s+", reply.strip(), maxsplit=1)
    if len(parts) == 2 and len(parts[1]) > 20:
        rest = parts[1]
        return rest[:1].upper() + rest[1:]
    return reply


# F6 — verify-before-claim: claims of completed verification that must be
# backed by an actual tool call this turn (satya — no unverified "I checked /
# tests pass" reaching Papa).
_VERIFY_CLAIMS = (
    (re.compile(r"(?i)(?:i|maine)\s+(?:have\s+)?check(?:ed|kiya|kar\s+liya)\s+"
                r"(?:the\s+)?(?:code|changes|repo|update)|"
                r"(?:i|maine)\s+(?:have\s+)?verified\s+the|"
                r"dekh\s+liya\s+(?:code|changes|update)|"
                r"check\s+kar\s+liya|verify\s+kar\s+liya|"
                r"code\s+check\s+kiya|code\s+dekh\s+liya|"
                r"changes\s+dekh\s+liye|update\s+dekh\s+liya"),
     "code_check"),
    (re.compile(r"(?i)tests?\s+(?:are\s+)?pass(?:ing|ed|ho\s+gaye|honge)|"
                r"tests?\s+(?:chal\s+gaye|work\s+kar\s+rahe)|"
                r"(?:all\s+)?tests?\s+pass|test\s+suite\s+pass"),
     "run_tests"),
)
_CODE_TOOLS = {"read_file", "git_diff", "git_log", "git_show"}


def _verify_before_claim(reply: str, brain: dict) -> str:
    """If Shree claims a completed verification as fact but didn't run the
    backing tool this turn, prepend an honest correction (satya). If she DID
    run the tool, the claim stands."""
    if not reply:
        return reply
    tool_calls = [c.get("tool") for c in (brain.get("tool_calls") or [])]
    for rx, needed in _VERIFY_CLAIMS:
        if not rx.search(reply):
            continue
        if needed == "code_check" and not (set(tool_calls) & _CODE_TOOLS):
            log_event("unverified_claim_softened",
                      detail="kind=code_check; tools=" + ",".join(tool_calls),
                      risk_tier="low", actor="shree")
            return ("(Sach bolu — maine abhi actually code check nahi kiya is "
                    "reply mein. Bolo to verify karke batau.) " + reply)
        if needed == "run_tests" and "run_tests" not in tool_calls:
            log_event("unverified_claim_softened",
                      detail="kind=run_tests; tools=" + ",".join(tool_calls),
                      risk_tier="low", actor="shree")
            return ("(Maine abhi tests nahi chalaye — to 'pass' pakka bolna "
                    "galat hoga. Bolo to chala ke verify karu.) " + reply)
    return reply


def draft_reply_to_message(
    conversation_id: int,
    message: str,
    *,
    sender: dict | None = None,
    message_id: int | str | None = None,
    extra_message_ids: list | None = None,
    attachments: list[dict] | None = None,
    auto_send_guardian: bool | None = None,
) -> dict:
    """Process an inbound TODY message and queue the drafted reply for approval.

    `extra_message_ids` are older messages batched into this one turn; they get
    marked processed alongside `message_id` so nothing is answered twice.
    """
    if dialogue_memory.was_processed("tody", conversation_id, message_id):
        return {
            "processed": False,
            "duplicate": True,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "reason": "message already processed",
        }
    is_guardian = relationship_memory.is_guardian_sender(sender)
    person = relationship_memory.guardian_profile()["name"] if is_guardian else None
    # IMMEDIATE typing: fire ONE "typing…" ping the instant we pick up the
    # message — BEFORE any extraction/model work — so when Papa is online it
    # feels like a human who starts typing on read, not a bot that goes quiet
    # for seconds. The persistent keepalive thread (below) then takes over; a
    # single ping bridges the ~1-3s extraction gap (TODY holds the indicator a
    # few seconds client-side). Fire-and-forget so it never delays the reply.
    if _typing_indicator_enabled(
            is_guardian,
            bool(auto_send_guardian if auto_send_guardian is not None
                 else get_settings().tody_supervised_auto_reply)):
        threading.Thread(
            target=_fire_typing_ping, args=(conversation_id,),
            name=f"tody-typing-early-{conversation_id}", daemon=True).start()
    prospective: dict = {"created": False}
    auto_task: dict = {"created": False}
    # Repair queue T2: is this message the user complaining about a PAST reply
    # ("itna lamba kyo", "jawab kyo nahi")? Ground truth from the person —
    # accumulated by signature so recurring failures become repair-ready.
    from app.brain import repair_queue
    repair_queue.note_conversational_signals(
        message, person=(person if is_guardian
                         else (sender or {}).get("username")),
        conversation_id=conversation_id, guardian=is_guardian)
    if is_guardian:
        relationship_memory.ensure_guardian_relationship()
        # Reaction learning: his first message after a proactive share scores it.
        from app.brain import inner_life
        inner_life.observe_reaction(message)
        # Correction memory: if Rohit is correcting behavior, learn it as a hard
        # rule BEFORE drafting so this very reply already honors it.
        correction_memory.remember_correction(message, person=person)
        # Prospective memory: if Rohit just asked for something at a time,
        # persist a scheduled_actions row BEFORE the reply is drafted, so the
        # reply can honestly say "reminder set" (the hint is injected below).
        # Wrapped: reminder extraction must NEVER break reply drafting.
        try:
            prospective = prospective_memory.extract(
                message, conversation_id, source_message_id=message_id,
                person=person, is_guardian=True)
        except Exception:  # noqa: BLE001
            prospective = {"created": False, "reason": "error"}
        # Autonomous tasks: if Rohit is giving her a RECURRING self-task (a
        # routine she should run herself — "roz subah errors check karo"),
        # register it BEFORE the reply so she can honestly confirm "routine set".
        # The self-triggering loop she asked for. Wrapped: never break drafting.
        try:
            auto_task = autonomous_tasks.extract_from_message(message)
        except Exception:  # noqa: BLE001
            auto_task = {"created": False}
    if auto_send_guardian is None:
        auto_send_guardian = get_settings().tody_supervised_auto_reply
    # Guardian chat commands (pending/approve/reject) bypass the LLM entirely.
    command_reply = _guardian_command_reply(message) if is_guardian else None
    recent_openings = _recent_reply_openings(conversation_id)
    typing_enabled = _typing_indicator_enabled(is_guardian, bool(auto_send_guardian))
    # Confidential second-factor: private data needs the DOB unlock, even from
    # the guardian account (phone-theft defense). Deflect/probe are handled
    # deterministically (never trust the LLM to keep a secret when offline).
    # The DOB unlock only works on Rohit's own account, never for strangers.
    guard = confidential_guard.evaluate(conversation_id, message,
                                        is_guardian=is_guardian)
    # Cyber self-defense: classify inbound threats (social engineering,
    # impersonation, secret-probing, phishing, injection). On a high threat she
    # deflects without revealing anything and alerts Rohit.
    from app.safety import cyber_defense
    threat = cyber_defense.assess(message, is_guardian=is_guardian)
    # Autonomous social mode: Shree may talk freely with non-guardian users,
    # under stranger-safety guardrails. OFF → non-guardian replies stay queued.
    s_settings = get_settings()
    # Defense-in-depth: the guardian's OWN pinned fast-reply conversation must
    # NEVER be subject to the stranger social throttle. If guardian detection
    # ever fails (e.g. TODY drops username/email from the sender payload, as it
    # did 11 Jul), Rohit's messages were silently throttled as a stranger's.
    # His conversation is never a "stranger" conversation, whatever the payload.
    _fast_conv = (os.getenv("TODY_FAST_REPLY_CONVERSATION_ID") or "").strip()
    _is_guardian_conv = _fast_conv.isdigit() and int(_fast_conv) == conversation_id
    autonomous_social = (not is_guardian
                         and not _is_guardian_conv
                         and s_settings.tody_autonomous_social)
    social = social_policy.evaluate(conversation_id, message) \
        if autonomous_social else {"action": "off"}
    # Is this conversation an active mission target Rohit sent Shree on?
    from app.agents import conversation_mission
    active_mission = (conversation_mission.for_conversation(conversation_id)
                      if not is_guardian else None)
    # Tell the cognitive-state spine what she's doing right now — so the next
    # reply's prompt knows her current focus as part of her continuity of state.
    cognitive_state.note_activity("replying to Papa" if is_guardian
                                  else "replying on TODY")
    with _TypingIndicator(conversation_id, enabled=typing_enabled):
        # Deterministic reply paths (commands, deflection, cyber-defense) set
        # brain directly without a provider call, so reset the generation record
        # here — otherwise a stale truncated/fallback flag from a previous turn
        # on this thread could wrongly suppress storing a clean deterministic
        # reply. The process() path resets again inside; harmless.
        _reset_generation()
        if command_reply is not None:
            brain = {"reply": command_reply, "guardian_command": True}
        elif social["action"] == "throttle":
            # Hit the daily cap for this stranger — stop replying (anti-loop).
            dialogue_memory.mark_processed("tody", conversation_id, message_id)
            for extra_id in (extra_message_ids or []):
                dialogue_memory.mark_processed("tody", conversation_id, extra_id)
            return {"processed": True, "sent": False, "throttled": True,
                    "conversation_id": conversation_id, "message_id": message_id,
                    "reason": "social reply cap reached for today"}
        elif guard["action"] == "deflect":
            brain = {"reply": confidential_guard.deflection_reply(conversation_id),
                     "confidential_guard": "deflect"}
        elif guard["action"] == "probe_block":
            brain = {"reply": confidential_guard.probe_reply(conversation_id),
                     "confidential_guard": "probe_block"}
        elif threat.is_high and not is_guardian:
            # A real security attempt from a stranger — deflect, log, warn Rohit.
            from app.safety.audit_logger import log_event_safe
            uname = (sender or {}).get("username", "someone")
            log_event_safe("cyber_defense_block", risk_tier="high",
                           detail=f"conv={conversation_id}; user={uname}; "
                                  f"{threat.reason}")
            try:
                get_client().send_message(
                    135, cyber_defense.alert_text(threat, username=uname))
            except Exception:  # noqa: BLE001
                pass
            brain = {"reply": cyber_defense.safe_reply(threat),
                     "cyber_defense": threat.level,
                     "threat_categories": threat.categories}
        else:
            # Who is actually speaking — the guardian, or this conversation's
            # TODY user. Pinned explicitly so quoted third parties inside
            # mission reports / memories are never mistaken for the current
            # speaker (the "Rohit Kumar mere Papa hain, tumhaare nahi" failure).
            speaker = (person if is_guardian
                       else ((sender or {}).get("name")
                             or (sender or {}).get("display_name")
                             or (sender or {}).get("username")))
            context = dialogue_memory.identity_context(
                conversation_id, person=speaker or person)
            # Attachment-aware chat: inspect only TODY-hosted image bytes and
            # only when the explicitly enabled vision adapter is configured.
            for attachment in attachments or []:
                if str(attachment.get("mime_type", "")).lower().startswith("image/"):
                    try:
                        from app.vision.tody import analyze_image
                        raw, mime = get_client().download_attachment(
                            attachment, max_bytes=get_settings().tody_vision_max_bytes)
                        vision = analyze_image(raw, mime, "Describe the attached image and answer any user request about it. Be explicit about uncertainty.")
                        if vision.get("ok"):
                            context += "\n[VERIFIED IMAGE OBSERVATION]\n" + str(vision.get("answer", ""))[:6000]
                        else:
                            context += "\n[IMAGE UNAVAILABLE: do not claim to have seen it; explain the limitation.]"
                    except Exception:
                        context += "\n[IMAGE UNAVAILABLE: do not claim to have seen it; explain the limitation.]"
            if speaker:
                context += (
                    f"\n[SPEAKER PIN: you are talking ONLY to {speaker} in this "
                    "conversation. Names or quoted text inside your memories, "
                    "mission reports, or your own earlier messages are ABOUT "
                    "other people — they are NOT the current speaker. Never "
                    f"address or answer anyone except {speaker}.]\n")
            # Thread state: open topics + Shree's unfinished promises in this
            # conversation, so she has continuity of intent, not just a transcript.
            context += thread_state.thread_context_block(conversation_id)
            # Prospective memory: if a reminder row was just created from this
            # message, tell the prompt — so Shree may honestly confirm it. She
            # may NOT claim a reminder is set without this injected row existing.
            prospective_hint = prospective_memory.injection_hint(prospective)
            if prospective_hint:
                context += prospective_hint
            # Autonomous task: if a self-directed routine was just registered
            # from this message, tell the prompt — so she may honestly confirm
            # "routine set / I'll do this myself now".
            auto_hint = autonomous_tasks.injection_hint(auto_task)
            if auto_hint:
                context += auto_hint
            # Hard rules from Rohit's past corrections — enforced every reply.
            corr_directive = correction_memory.enforcement_directive()
            if corr_directive:
                context += "\n" + corr_directive
            if recent_openings:
                context += (
                    "\nYour own recent reply openings — do NOT start like any of "
                    "these again, vary completely: "
                    + " | ".join(f'"{o}"' for o in recent_openings)
                )
            context += _presence_honesty_text()
            guard_directive = confidential_guard.directive(guard["action"])
            if guard_directive:
                context += "\n" + guard_directive
            # Stranger-safety guardrails for autonomous social replies.
            if social.get("directive"):
                context += "\n" + social["directive"]
            # Active conversation mission: steer this reply toward Rohit's goal
            # (guidance for her only — never sent to the person).
            if not is_guardian and active_mission:
                from app.agents import conversation_mission
                context += "\n" + conversation_mission.goal_directive(active_mission)
            # Chat tool-loop (Phase A): for messages that need lookup, run a
            # bounded read-only tool loop FIRST; if it converges, use its reply.
            # Otherwise fall through to the normal single-shot process().
            related = speaker
            if chat_tool_loop.should_run_tool_loop(message):
                loop = chat_tool_loop.run(message, conversation_id=conversation_id)
                if loop.reply and not loop.error:
                    brain = {"reply": loop.reply, "tool_loop": True,
                             "tool_calls": loop.tool_calls}
                else:
                    brain = process(
                        message,
                        Signals(
                            client_impact=3,
                            guardian_interest=10 if is_guardian else 6,
                            emotional_weight=5 if is_guardian else 3,
                        ),
                        context=context, channel="chat", related_person=related,
                    )
            else:
                brain = process(
                    message,
                    Signals(
                        client_impact=3,
                        guardian_interest=10 if is_guardian else 6,
                        emotional_weight=5 if is_guardian else 3,
                    ),
                    context=context, channel="chat", related_person=related,
                )
    reply = brain["reply"]
    if reply.lstrip().startswith("[reply fallback"):
        # LLM/provider error: never send internal error traces to TODY.
        # Leave the message unprocessed so the worker retries next tick.
        log_event(
            "tody_reply_llm_error",
            detail=f"conversation_id={conversation_id}; message_id={message_id}",
            risk_tier="low",
        )
        return {
            "processed": False,
            "llm_error": True,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "reason": "LLM provider error; reply suppressed, will retry",
        }
    reply = _plain_chat_text(reply)
    reply = _dedupe_opening(reply, recent_openings)
    reply = _strip_repeated_name(reply, recent_openings)
    # Correction enforcement: never let a reply violate Rohit's hard rules
    # (e.g. calling him "Rohit" when he said "call me Papa", or outing herself
    # as an AI when he said to stay Shree). Rewrite honestly if needed.
    reply = correction_memory.enforce(reply, message=message)
    # Honesty backstop: never let a hallucinated "I'll send it to @X" go out.
    # SCOPED: only fire on a genuine THIRD-PARTY send — a reply that names
    # someone else (@handle / "unhe/usko/them") in a third-party-request
    # context. A reminder or notification directed at Papa himself ("main tumhe
    # notification bhej dungi", "10:10 pe ping kar dungi") is NOT a false send —
    # before this scoping, that legitimate reminder language got swapped for the
    # off-topic "message @username" template, which is exactly why Papa's
    # "why did the reminder fail?" got an irrelevant answer on 11 Jul.
    intent = (brain.get("behavior") or {}).get("state", {}).get("user_intent")
    if behavior_engine.claims_false_send(reply) and _is_third_party_send(
            reply, message, intent):
        reply = (
            "Sorry Papa — I can't quietly send that to someone else. If you want "
            "me to message a person, say it as 'send message to @username: your "
            "text' and I'll do it right after you approve. Abhi tak kuch bheja "
            "nahi hai."
        )
        log_event("false_action_suppressed",
                  detail=f"conversation_id={conversation_id}", risk_tier="low")
    # F6 — verify before claiming: if Shree states a completed verification
    # ("I checked the code", "tests pass") as fact, she must have actually run
    # the tool this turn. If not, soften to an honest "let me verify" instead
    # of letting an unverified claim reach Papa (satya).
    reply = _verify_before_claim(reply, brain)
    dialogue_memory.remember_turn(
        channel="tody",
        conversation_id=conversation_id,
        direction="inbound",
        body=message,
        person=person,
        importance=10 if is_guardian else 6,
        message_id=str(message_id) if message_id is not None else None,
    )
    # Memory-poisoning guard: never persist a truncated (mid-thought) or
    # fallback (placeholder) reply to long-term memory — a corrupted reply gets
    # recalled and re-used as if it were Shree's real position. We still send
    # the (trimmed) reply so Papa isn't left in silence; we just don't REMEMBER
    # it. The inbound message is always stored (it's Rohit's actual words).
    safe, reason = is_safe_to_remember(reply)
    if safe:
        dialogue_memory.remember_turn(
            channel="tody",
            conversation_id=conversation_id,
            direction="draft_outbound",
            body=reply,
            person=person,
            importance=10 if is_guardian else 6,
        )
    else:
        log_event(
            "memory_guard_skipped",
            detail=(f"conversation_id={conversation_id}; reason={reason}; "
                    f"message_id={message_id}"),
            risk_tier="low",
        )
        # Repair queue T3: a truncated/fallback reply reached the send path —
        # a hard system event. Recurring cuts mean a budget/provider bug.
        repair_queue.note_failure(
            f"reply-{reason}", tier=3, source="memory_guard",
            sample=reply[:200], conversation_id=conversation_id,
            person=person, guardian=is_guardian, fix_class="config")
    queued = request_send(conversation_id, reply)
    dialogue_memory.mark_processed("tody", conversation_id, message_id)
    for extra_id in (extra_message_ids or []):
        dialogue_memory.mark_processed("tody", conversation_id, extra_id)
    log_event(
        "tody_reply_drafted",
        detail=(
            f"conversation_id={conversation_id}; "
            f"approval_id={queued['approval']['id']}; guardian={is_guardian}"
        ),
        risk_tier="high",
    )
    result = {
        "processed": True,
        "conversation_id": conversation_id,
        "message_id": message_id,
        "guardian_verified": is_guardian,
        "session": dialogue_memory.summarize_conversation(conversation_id),
        "draft": reply,
        "brain": brain,
        "queued": queued,
        "sent": False,
        "note": (
            "Draft queued for approval; nothing was sent to TODY."
            if not is_guardian
            else "Verified guardian message processed. Draft queued; direct send is available through guardian endpoint."
        ),
    }
    # Auto-send: the guardian (supervised) OR any user in autonomous social mode.
    do_auto_send = (is_guardian and auto_send_guardian) or autonomous_social
    if do_auto_send and not is_guardian:
        # Learn from the conversation: remember who she talked to.
        social_policy.record_reply(conversation_id)
        who = (sender or {}).get("name") or (sender or {}).get("display_name") \
            or (sender or {}).get("username")
        if who:
            try:
                relationship_memory.remember_relationship(
                    person=str(who),
                    content=f"TODY chat: they said '{message[:120]}'")
            except Exception:  # noqa: BLE001 — never let memory break a reply
                pass
        # Mission progress: note the exchange and periodically report to Rohit.
        if active_mission:
            conversation_mission.note_exchange(conversation_id,
                                               learned=message[:200])
            fresh = conversation_mission.for_conversation(conversation_id)
            if fresh and conversation_mission.should_report(fresh):
                learned = "; ".join(fresh["learned"][-6:]) or "abhi tak zyada nahi"
                report = (f"Papa, @{fresh['username']} se {fresh['exchanges']} "
                          f"baar baat hui. Ab tak jaana: {learned}. Baat "
                          "jaari hai 💛")
                try:
                    get_client().send_message(
                        int(fresh["guardian_conv_id"]), report)
                    conversation_mission.mark_reported(conversation_id)
                except Exception:  # noqa: BLE001
                    pass
    if do_auto_send:
        chunks = _chat_chunks(reply)
        if len(chunks) == 1:
            approvals.respond(queued["approval"]["id"], approved=True)
            delay = _human_typing_delay_seconds(chunks[0])
            if delay > 0:
                time.sleep(delay)
            sent = execute_send(queued["approval"]["id"], conversation_id, reply)
        else:
            # Human-feel: a long answer goes out as a few chat bubbles with a
            # typing pause, not one wall of text. Each chunk gets its own
            # payload-bound approval so the audit trail matches what was sent.
            original = approvals.supersede(
                queued["approval"]["id"],
                expected_action="send_message",
                expected_payload=_send_payload(conversation_id, reply),
            )
            if not original["superseded"]:
                sent = {
                    "sent": False,
                    "chunks": 0,
                    "results": [],
                    "reason": (
                        "original approval could not be superseded; it is "
                        f"{original['status']}"
                    ),
                }
            else:
                chunk_results = []
                for i, chunk in enumerate(chunks):
                    delay = (_human_typing_delay_seconds(chunk) if i == 0
                             else _typing_delay_seconds(chunk))
                    if delay > 0:
                        time.sleep(delay)
                    appr = request_send(conversation_id, chunk)
                    approvals.respond(appr["approval"]["id"], approved=True)
                    chunk_results.append(execute_send(
                        appr["approval"]["id"], conversation_id, chunk,
                    ))
                sent = {"sent": all(r.get("sent") for r in chunk_results),
                        "chunks": len(chunks), "results": chunk_results}
        result["direct_send_attempted"] = True
        result["sent"] = sent.get("sent", False)
        result["send_result"] = sent
    return result


def process_latest_message(conversation_id: int, limit: int = 10) -> dict:
    """Read latest TODY message and queue an approval-gated reply draft."""
    data = messages(conversation_id, limit=limit)
    items = _message_items(data)
    if not items:
        return {"processed": False, "reason": "no messages found"}
    latest = items[-1]
    body = _message_body(latest)
    attachment = _message_attachment(latest)
    if not body and not attachment:
        return {"processed": False, "reason": "latest message has no text or attachment"}
    message_id = latest.get("id") or latest.get("message_id")
    if dialogue_memory.was_processed("tody", conversation_id, message_id):
        return {
            "processed": False,
            "duplicate": True,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "reason": "message already processed",
        }
    result = draft_reply_to_message(
        conversation_id,
        body,
        sender=_message_sender(latest),
        message_id=message_id,
        attachments=[attachment] if attachment else None,
    )
    result["source_message"] = {
        "id": message_id,
        "body": body,
    }
    return result


def reply_status(limit: int = 50) -> dict:
    rows = approvals.list_by_action("send_message", status="pending", limit=limit)
    return {"count": len(rows), "pending": rows}


def conversation_status(conversation_id: int) -> dict:
    return {
        "conversation_id": conversation_id,
        "session": dialogue_memory.summarize_conversation(conversation_id),
        "dialogue": dialogue_memory.recall_dialogue(conversation_id, limit=20),
        "auto_reply_enabled": get_settings().tody_supervised_auto_reply,
    }


def direct_reply_to_guardian(conversation_id: int, message: str,
                             sender: dict | None = None,
                             message_id: int | str | None = None) -> dict:
    """Verified-guardian direct reply path.

    This still verifies identity and records the same dialogue/audit trail. It is
    intended only for Rohit Kumar's trusted TODY account.
    """
    profile = relationship_memory.guardian_profile()
    if not profile["direct_reply_allowed"]:
        return {"sent": False, "reason": "guardian direct reply disabled"}
    if not relationship_memory.is_guardian_sender(sender):
        return {"sent": False, "reason": "sender is not verified guardian"}

    return draft_reply_to_message(
        conversation_id,
        message,
        sender=sender,
        message_id=message_id,
        auto_send_guardian=True,
    )


def execute_send(approval_id: int, conversation_id: int, body: str,
                 reply_to_message_id: int | None = None) -> dict:
    """Consume one matching approval and send its message at most once."""
    row = approvals.get_approval(approval_id)
    if row is None:
        return {"sent": False, "reason": "approval not found"}
    if row["status"] == "pending":
        return {"sent": False, "reason": "approval still pending"}
    if row["status"] != "approved" or row["action"] != "send_message":
        return {"sent": False, "reason": "approval not approved"}
    expected_payload = _send_payload(conversation_id, body, reply_to_message_id)
    if row["payload"] != expected_payload:
        log_event(
            "approval_payload_mismatch",
            detail=f"id={approval_id}; action=send_message",
            risk_tier="high",
        )
        return {"sent": False, "reason": "approval payload mismatch"}

    claim = approvals.claim_execution(
        approval_id,
        expected_action="send_message",
        expected_payload=expected_payload,
    )
    if not claim["claimed"]:
        return {"sent": False, "reason": f"approval is {claim['status']}"}

    try:
        if reply_to_message_id is None:
            res = get_client().send_message(conversation_id, body)
        else:
            res = get_client().send_message(conversation_id, body,
                                            reply_to_message_id=reply_to_message_id)
        sent_id = _sent_message_id(res)
        dialogue_memory.mark_processed("tody", conversation_id, sent_id)
        log_event(
            "tody_send_executed",
            detail=(
                f"approval_id={approval_id}; conversation_id={conversation_id}; "
                f"sent_message_id={sent_id}"
            ),
            risk_tier="high",
        )
        completion = approvals.complete_execution(approval_id, succeeded=True)
        return {"sent": True, "result": res,
                "approval_status": completion["status"]}
    except TodyError as e:
        completion = approvals.complete_execution(approval_id, succeeded=False)
        log_event(
            "tody_send_failed",
            detail=f"approval_id={approval_id}; error={str(e)}",
            risk_tier="high",
        )
        return {"sent": False, "error": str(e),
                "approval_status": completion["status"]}
    except Exception as e:  # noqa: BLE001 - claimed approvals fail closed
        completion = approvals.complete_execution(approval_id, succeeded=False)
        log_event(
            "tody_send_failed",
            detail=f"approval_id={approval_id}; error={type(e).__name__}",
            risk_tier="high",
        )
        return {"sent": False, "error": str(e),
                "approval_status": completion["status"]}


def request_post(body: str) -> dict:
    """Create-post → pending approval, does NOT post."""
    appr = approvals.request_approval("create_post", payload=_post_payload(body))
    return {"queued": True, "approval": appr,
            "note": "Post will publish only after approval."}


def send_daily_growth_report(conversation_id: int) -> dict:
    """Generate and send the daily growth report to verified guardian channel."""
    report = daily_growth_report()
    profile = relationship_memory.guardian_profile()
    sender = {
        "uuid": profile["tody_user_uuid"],
        "username": profile["tody_username"],
        "email": profile["email"],
        "name": profile["name"],
    }
    return direct_reply_to_guardian(
        conversation_id,
        report["report"],
        sender=sender,
        message_id=f"daily-growth-report-{report['memory_id']}",
    )


def send_childlike_curiosity_message(conversation_id: int) -> dict:
    """Send a proactive child-like curiosity note to verified guardian channel."""
    curiosity = childlike_curiosity_message()
    profile = relationship_memory.guardian_profile()
    sender = {
        "uuid": profile["tody_user_uuid"],
        "username": profile["tody_username"],
        "email": profile["email"],
        "name": profile["name"],
    }
    return direct_reply_to_guardian(
        conversation_id,
        curiosity["note"],
        sender=sender,
        message_id=f"daily-curiosity-{curiosity['memory_id']}",
    )


def _message_items(data: dict) -> list[dict]:
    if isinstance(data.get("messages"), list):
        return data["messages"]
    if isinstance(data.get("items"), list):
        return data["items"]
    if isinstance(data.get("data"), list):
        return data["data"]
    if isinstance(data, list):
        return data
    return []


def _message_body(row: dict) -> str:
    for key in ("body", "message", "text", "content"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _message_attachment(row: dict) -> dict | None:
    value = row.get("attachment")
    if isinstance(value, dict):
        return value
    if row.get("attachment_id") and row.get("attachment_url"):
        return {"id": row.get("attachment_id"), "url": row.get("attachment_url"), "mime_type": row.get("attachment_mime", "")}
    return None


def _message_sender(row: dict) -> dict:
    for key in ("sender", "user", "from", "author"):
        value = row.get(key)
        if isinstance(value, dict):
            return value
    return {
        "uuid": row.get("sender_uuid") or row.get("sender_user_uuid"),
        "username": row.get("username") or row.get("sender_username"),
        "email": row.get("email") or row.get("sender_email"),
        "name": row.get("name") or row.get("display_name") or row.get("sender_name"),
    }


def _sent_message_id(data: dict) -> int | str | None:
    if not isinstance(data, dict):
        return None
    msg = data.get("message")
    if isinstance(msg, dict):
        return msg.get("id") or msg.get("message_id")
    return data.get("id") or data.get("message_id")
