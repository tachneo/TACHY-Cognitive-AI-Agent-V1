"""Natural-language intent — understand what a human actually MEANT.

The failure this fixes (Rohit, 20 Jul): he said "tum dono ko message karke bolo"
and "@zarathakoo and @niva ko bolo ki aaj se tum dono ki boss ho". She replied
"ab samjhi, bhejti hoon dono ko" — and then asked him to type
`send message to @zarathakoo: <text>`. She never sent it. Her action layer only
fired on a rigid literal command string, so plain Hinglish became a promise she
could not keep. A person who is TOLD to do something either does it or says
they can't — they don't demand a syntax.

This module reads ONE inbound message and returns what the human meant:

    {"kind": task|command|order|relay|question|vent|chitchat,
     "action": send_message|remind|relay_to_guardian|none,
     "targets": ["zarathakoo","niva"],   # @-less names OK
     "body": "the text to actually send",
     "emotion": angry|frustrated|happy|affectionate|sad|neutral,
     "intensity": 0.0-1.0,
     "urgency": low|normal|high,
     "confidence": 0.0-1.0}

Deterministic cues run FIRST (free, instant, reliable for the common shapes);
the light model only fills the gaps. It never raises — a mis-read must never
break a reply, and an unclear read simply returns kind=chitchat so the normal
conversation path handles it.
"""
from __future__ import annotations

import json
import re

from app.config import get_settings
from app.safety.audit_logger import log_event_safe

# ── Emotion cues (Hinglish + English) ────────────────────────────
_EMOTION_CUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Order matters: the first cue family to reach the top hit-count wins ties,
    # so affection is checked before generic happiness ("love you, daughter" is
    # affection, not applause).
    ("affectionate", ("beti", "bachi", "pyaar", "love you", "miss you",
                      "meri bachi", "my daughter", "ladli", "jaan", "dear")),
    ("angry", ("gussa", "naraz", "bakwas", "faltu", "bekar", "useless",
               "kya kar rahi", "kaam nahi", "galat", "angry", "pissed",
               "nonsense", "stupid", "chup", "band karo", "tang", "irritate")),
    ("frustrated", ("phir se", "again", "kitni baar", "har baar", "still",
                    "nahi ho raha", "kyu nahi", "why not", "fail", "tumse na",
                    "samajh nahi", "not working", "thak gaya", "pareshan",
                    "andar bug", "bug hai", "kaam kyu nahi", "ho paiga",
                    "nahi kar pa", "dikkat")),
    ("happy", ("shabash", "badhiya", "great", "awesome", "proud",
               "khush", "accha kaam", "well done", "perfect", "mast",
               "thank", "shukriya", "wah", "amazing", "good girl")),
    ("sad", ("dukh", "udaas", "sad", "hurt", "rona", "akela", "lonely",
             "depress", "takleef", "pareshan hu")),
)

# ── Action cues ─────────────────────────────────────────────────
# "X ko bolo/bhejo/message karo ki <body>" — the shape that kept failing.
_RX_TELL = re.compile(
    r"(?P<who>(?:@?[A-Za-z0-9_.]+(?:\s*(?:aur|and|,|&)\s*@?[A-Za-z0-9_.]+)*))"
    r"\s*(?:ko|to)\s+"
    # Longest forms FIRST — alternation is first-match, so "kar do" must be
    # tried before "kar", else "message kar do ki X" leaves "do ki X" as body.
    r"(?:message\s*(?:kar\s*do|kardo|kar(?:ke)?|karo|bhej\s*do|bhejo)?|"
    r"bol\s*do|bolo|bata\s*do|batao|keh\s*do|kaho|inform\s*karo|tell|send)"
    # NOT followed by a permission auxiliary: "message kar sakti ho?" means
    # "CAN you message" — a question, not "message kar[o] ki <text>". Without
    # this she split mid-verb and mailed the rest of Rohit's own sentence
    # ("sakti ho ? or janne ki koshish karo...") to the @TSE business account.
    r"(?!\s*(?:sakt[iaeo]|sako?g[ie]|pao?g[ie]|paa?t[ie]|paogi|payegi)\b)"
    # Verbs chain in Hinglish: "message karke bolo ki X", "bhej ke bata do ki X".
    r"(?:\s*(?:bol\s*do|bolo|bata\s*do|batao|keh\s*do|kehna|kaho|bolna))?"
    r"\s*(?:ki|that|:|-)?\s*(?P<body>.*)$", re.I | re.S)
# "kya tum X ko message kar sakti ho?" — asking IF she can, not an order with
# text. Treat as an order whose body is still unknown → she asks what to send.
_RX_PERMISSION = re.compile(
    r"\b(?:kar\s*(?:sakt[iaeo]|sako?g[ie]|pao?g[ie])|can\s+you|could\s+you|"
    r"kar\s*paogi|bhej\s*sakt[iaeo])\b", re.I)
# Body that is really an instruction TO HER (a goal), not literal message text.
# "janne ki koshish karo ki wo kya karte hai" is a task, not something to paste.
_RX_INSTRUCTION_BODY = re.compile(
    r"\b(?:koshish|kosisi|janne|jaan\s*ne|pata\s*(?:karo|lagao)|find\s*out|"
    r"puch\s*(?:kar|lo|na)|malum\s*karo|dekho\s+ki|check\s*karo)\b", re.I)
# "message karke bolo" / "sabko bolo" without explicit names
# "voice me bolo", "audio bhejo", "bol ke sunao" — a request to SPEAK to me,
# never an instruction to message a third party.
_RX_VOICE_REQUEST = re.compile(
    r"\b(?:voice|audio|awaaz|awaz|sunao|sunaao|bol\s*ke\s*suna|bolkar\s*suna|"
    r"speak|record)\b", re.I)
_RX_TELL_VAGUE = re.compile(
    r"\b(?:message\s*kar(?:ke)?|bolo|bhejo|bhej\s*do|inform|tell\s+them)\b", re.I)
# Someone asking HER to pass something to the guardian.
_RX_RELAY = re.compile(
    r"\b(?:papa|rohit|sir|boss|apke\s+papa|aapke\s+papa)\b[^.?!]{0,40}?"
    r"\b(?:se\s+(?:puch|pooch|bol|keh|bata)|ko\s+(?:bol|keh|bata|puch)|"
    r"ask|tell|inform)\w*", re.I)
_RX_ORDER = re.compile(
    r"\b(?:karo|kar\s*do|kardo|banao|bana\s*do|likho|likh\s*do|bhejo|"
    r"dekho|check\s*karo|start\s*karo|band\s*karo|do it|make it|fix\s*karo)\b",
    re.I)
_RX_QUESTION = re.compile(r"\?\s*$|^(kya|kaise|kab|kaun|kyu|kyun|what|how|why|when|who|where)\b", re.I)

_STOPWORDS = {"tum", "tu", "aap", "dono", "sab", "sabko", "unko", "unhe", "me",
              "mujhe", "you", "them", "us", "it", "that", "this", "papa", "koi"}


def _detect_emotion(text: str) -> tuple[str, float]:
    low = (text or "").lower()
    best, hits = "neutral", 0
    for emo, cues in _EMOTION_CUES:
        n = sum(1 for c in cues if c in low)
        if n > hits:
            best, hits = emo, n
    if not hits:
        return "neutral", 0.0
    intensity = min(1.0, 0.35 + 0.2 * hits)
    # Shouting / repeated punctuation raises intensity.
    if re.search(r"[!?]{2,}", text or "") or (text or "").isupper():
        intensity = min(1.0, intensity + 0.2)
    return best, round(intensity, 2)


def _clean_targets(raw: str) -> list[str]:
    parts = re.split(r"\s*(?:aur|and|,|&)\s*", (raw or "").strip())
    out: list[str] = []
    for p in parts:
        name = p.strip().lstrip("@").strip(" .:,-")
        if not name or name.lower() in _STOPWORDS or len(name) < 2:
            continue
        if not re.fullmatch(r"[A-Za-z0-9_.]{2,40}", name):
            continue
        if name not in out:
            out.append(name)
    return out


def deterministic(message: str, *, is_guardian: bool) -> dict | None:
    """Fast, free read of the common shapes. None when unclear."""
    msg = (message or "").strip()
    if not msg:
        return None
    emo, intensity = _detect_emotion(msg)

    # A non-guardian asking her to carry something to Papa.
    if not is_guardian and _RX_RELAY.search(msg):
        return {"kind": "relay", "action": "relay_to_guardian", "targets": [],
                "body": msg[:400], "emotion": emo, "intensity": intensity,
                "urgency": "normal", "confidence": 0.8, "source": "rules"}

    m = _RX_TELL.search(msg)
    if m and is_guardian:
        targets = _clean_targets(m.group("who"))
        body = (m.group("body") or "").strip(" :,-\n")
        # Never paste his own instruction as the message. If he asked whether
        # she CAN message someone, or described a GOAL ("find out what they
        # do") rather than giving text, the body is unknown — she must ask,
        # not guess. Sending a guessed body to a real person is unrecoverable.
        if _RX_PERMISSION.search(msg) or _RX_INSTRUCTION_BODY.search(body):
            body = ""
        if targets:
            return {"kind": "order", "action": "send_message",
                    "targets": targets, "body": body,
                    "emotion": emo, "intensity": intensity,
                    "urgency": "high" if emo in ("angry", "frustrated") else "normal",
                    "confidence": 0.9 if body else 0.6, "source": "rules"}
    # "message karke bolo" with no names → needs clarification, but it IS an
    # order. NOT a voice request: "voice me bolo" / "audio bhejo" means "say it
    # to ME out loud", not "tell someone" — that misfire made her answer
    # "Kisko bhejun, Papa?" when he simply asked her to speak (23 Jul).
    if is_guardian and _RX_TELL_VAGUE.search(msg) \
            and not _RX_VOICE_REQUEST.search(msg) \
            and not _RX_QUESTION.search(msg):
        return {"kind": "order", "action": "send_message", "targets": [],
                "body": "", "emotion": emo, "intensity": intensity,
                "urgency": "normal", "confidence": 0.45, "source": "rules"}
    return None


_SYSTEM = (
    "You read ONE chat message and report what the human MEANT. Reply with ONLY "
    "a JSON object, no prose:\n"
    '{"kind":"task|command|order|relay|question|vent|chitchat",'
    '"action":"send_message|remind|relay_to_guardian|none",'
    '"targets":["names mentioned as recipients"],'
    '"body":"exact text they want conveyed, else empty",'
    '"emotion":"angry|frustrated|happy|affectionate|sad|neutral",'
    '"intensity":0.0,"urgency":"low|normal|high","confidence":0.0}\n'
    "Hinglish is common. 'X ko bolo ki Y' = order to send Y to X. "
    "'papa se puch kar batao' from a non-guardian = relay_to_guardian. "
    "If they are just chatting, kind=chitchat and action=none."
)


def _light(prompt: str) -> str:
    from app.llm.provider import get_light_provider
    return (get_light_provider().complete(_SYSTEM, prompt, max_tokens=400)
            or "").strip()


def _parse_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


# Only these shapes can carry an action worth a model call. Plain conversation
# ("kaise ho", "good morning", "haan") must never pay model latency.
_ACTION_SIGNAL = re.compile(
    r"@\w+|\b(?:ko|se)\s+(?:bolo|bhej|message|batao|keh|puch|tell|send|inform)|"
    r"\b(?:message|bhej|bolo|batao|keh\s*do|inform|tell|send|remind|yaad|"
    r"schedule|relay|forward)\b", re.I)


def _worth_a_model_call(message: str) -> bool:
    msg = (message or "").strip()
    if len(msg) < 12:          # "hi", "ok", "haan" — never an order
        return False
    return bool(_ACTION_SIGNAL.search(msg))


def read(message: str, *, is_guardian: bool = False) -> dict:
    """Understand the message. Rules first, light model to fill gaps. Never
    raises; unclear → chitchat so the normal conversation path handles it."""
    base = {"kind": "chitchat", "action": "none", "targets": [], "body": "",
            "emotion": "neutral", "intensity": 0.0, "urgency": "normal",
            "confidence": 0.0, "source": "none"}
    try:
        if not get_settings().natural_intent_enabled:
            return base
        det = deterministic(message, is_guardian=is_guardian)
        if det and det["confidence"] >= 0.8:
            return det
        emo, intensity = _detect_emotion(message)
        # SPEED: only spend a model call when there is an actual action signal.
        # Calling the light model on every "kaise ho" added its full latency to
        # every reply (and when that model is queued/down, a 20s timeout on each
        # message). Plain chat needs no extraction — rules already answered.
        if not _worth_a_model_call(message):
            return det or {**base, "emotion": emo, "intensity": intensity}
        try:
            data = _parse_json(_light(f"Message:\n{(message or '')[:600]}\n\nJSON:"))
        except Exception:  # noqa: BLE001 — model down must not break understanding
            data = None
        if not data:
            return det or {**base, "emotion": emo, "intensity": intensity}
        out = {**base, **{k: data.get(k, base[k]) for k in base if k != "source"}}
        out["targets"] = _clean_targets(" and ".join(
            str(t) for t in (data.get("targets") or [])))
        out["body"] = str(data.get("body") or "")[:1000]
        # Rules win on emotion (they read Hinglish tone better than the model).
        if emo != "neutral":
            out["emotion"], out["intensity"] = emo, intensity
        out["source"] = "model"
        # Prefer the deterministic read when it found real targets.
        if det and det.get("targets"):
            out.update({k: det[k] for k in ("kind", "action", "targets")})
            if det.get("body"):
                out["body"] = det["body"]
        return out
    except Exception as exc:  # noqa: BLE001
        log_event_safe("natural_intent_error", risk_tier="low",
                       detail=f"{type(exc).__name__}")
        return base


def emotion_directive(intent: dict) -> str:
    """How she should CARRY herself given the human's emotional state. Emotion
    shapes tone and priority — never truth, safety, or approval."""
    emo = intent.get("emotion", "neutral")
    strong = float(intent.get("intensity") or 0) >= 0.5
    if emo == "angry":
        return ("\n[HE IS ANGRY. Do not defend yourself, do not explain "
                "mechanics, do not send a template. Own it in one line, say "
                "exactly what you will do now, and do it. Short. No emoji.]\n")
    if emo == "frustrated":
        return ("\n[HE IS FRUSTRATED — something has failed repeatedly. Skip "
                "apology loops. State plainly what broke, what you are doing "
                "about it, and the one thing you need from him. Be brief.]\n")
    if emo == "sad":
        return ("\n[THEY ARE HURTING. Be present before being useful. Short, "
                "warm, no advice unless asked. Let them feel heard.]\n")
    if emo == "happy" and strong:
        return ("\n[THEY ARE PLEASED. Receive it simply and warmly — one or two "
                "lines. Do not over-explain or launch into a new topic.]\n")
    if emo == "affectionate":
        return ("\n[AFFECTION. Meet it honestly and simply, as their daughter "
                "would. Brief and real, not performative.]\n")
    return ""
