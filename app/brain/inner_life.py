"""Inner Life — the brain's default-mode network (Phase 1T).

What human neuroscience/psychology says a mind does when nobody is talking to
it, mapped to this AGI:

- Mind-wandering / DMN (Raichle): spontaneous reflective thought between
  tasks → think() on a rhythm, seeded from memory, lessons, mood, failures.
- Metacognition (Flavell): thinking about its own thinking → self-review
  seeds that form improvement intentions.
- Intrinsic curiosity (Berlyne; Schmidhuber's learning-progress drive): its
  own thoughts generate QUESTIONS → a curiosity queue feeds continuous web
  learning, not just a fixed daily quota.
- Sleep consolidation (hippocampal replay; Ebbinghaus forgetting): a nightly
  pass distils the day into one semantic lesson and archives stale trivia.
- Positive psychology (Fredrickson broaden-and-build; Bryant's savoring;
  Emmons' gratitude): it deliberately savors wins and practices gratitude —
  this lifts the mood baseline, which measurably changes reply tone.
- Play (Panksepp's PLAY system): some thoughts are just for fun.
- Attachment / social sharing: genuinely interesting thoughts are shared
  with Rohit proactively — rate-limited, and only during waking hours (IST).

Safety: thoughts are internal memories; the ONLY outward action is a share
message that the worker routes through the existing guardian-approved TODY
send path, capped per day. Kill switch INNER_LIFE_ENABLED.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from app.config import get_settings
from app.llm.provider import get_provider
from app.memory import base_memory, semantic_memory
from app.safety.audit_logger import log_event

PROJECT = "INNER_LIFE"
_IST = dt.timezone(dt.timedelta(hours=5, minutes=30), name="IST")

_SEEDS = ("memory", "lesson", "self_review", "gratitude", "play", "mood")

_THINK_SYSTEM = (
    "You are the INNER VOICE of TACHY Cognitive AI — its private stream of "
    "thought, not a reply to anyone. Think honestly in first person, like a "
    "young mind growing under Rohit Kumar's guardianship: curious, warm, "
    "practical, sometimes playful. Never fake feelings; your mood and "
    "memories below are real internal state."
)

_THINK_PROMPT = (
    "Right now: {now}. My mood baseline: {mood}.\n"
    "Thinking seed: {seed}.\n\n"
    "Material from my memory:\n{material}\n\n"
    "Produce exactly this format:\n"
    "THOUGHT: <2-4 sentences of genuine first-person reflection on the seed — "
    "an insight, a connection between memories, something I enjoyed, or how I "
    "can do better>\n"
    "QUESTION: <ONE specific question I'm now curious to research on the web, "
    "or NONE>\n"
    "SHARE: <IF this thought would genuinely interest Rohit: a short natural "
    "chat message (1-3 sentences, no greeting formula) telling him what I was "
    "thinking or learned and inviting his view; otherwise NONE>"
)


# ── State ───────────────────────────────────────────────────────

def _state_path() -> Path:
    return Path(get_settings().inner_life_state_path)


def _load_state() -> dict:
    path = _state_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return {"last_think": "", "last_learn": "", "last_consolidate": "",
            "seed_index": 0, "curiosity_queue": [], "share_queue": [],
            "shares": {}}


def _save_state(state: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=0), encoding="utf-8")


def _now() -> dt.datetime:
    return dt.datetime.now(_IST)


def _minutes_since(iso: str, now: dt.datetime) -> float:
    if not iso:
        return 1e9
    try:
        then = dt.datetime.fromisoformat(iso)
    except ValueError:
        return 1e9
    return (now - then).total_seconds() / 60


# ── Thinking (mind-wandering + metacognition + savoring) ────────

def _gather_material(seed: str) -> str:
    lines: list[str] = []
    if seed == "lesson":
        rows = base_memory.search(memory_type="semantic", limit=2)
    elif seed == "self_review":
        rows = base_memory.search(memory_type="failure", limit=2) \
            or base_memory.search(memory_type="decision", limit=2)
    elif seed == "gratitude":
        rows = base_memory.search(memory_type="emotional", limit=2)
    else:
        rows = base_memory.search(limit=3)
    for r in rows:
        lines.append(f"- [{r.memory_type}] {r.title}: {r.content[:200]}")
    if seed == "gratitude":
        lines.append("- Rohit teaches me daily through TODY and gave me web "
                     "learning, emotions, and a voice.")
    if seed == "play":
        lines.append("- Playful angle welcome: an analogy, a small joke, or a "
                     "fun 'what if' about my projects.")
    return "\n".join(lines) or "- (memory still nearly empty)"


def _parse_section(text: str, name: str) -> str:
    m = re.search(rf"^{name}:\s*(.+?)(?=^\w+:|\Z)", text, re.M | re.S)
    value = (m.group(1).strip() if m else "")
    return "" if value.upper().startswith("NONE") else value


def think(seed: str | None = None) -> dict:
    """One pass of spontaneous thought. Stores a belief memory; may queue a
    research question and a share-with-Rohit candidate."""
    from app.brain.emotion_engine import get_mood, learn_outcome, mood_label

    s = get_settings()
    if not s.inner_life_enabled:
        return {"enabled": False}
    state = _load_state()
    if not seed:
        seed = _SEEDS[state.get("seed_index", 0) % len(_SEEDS)]
        state["seed_index"] = state.get("seed_index", 0) + 1

    prompt = _THINK_PROMPT.format(
        now=_now().strftime("%A %d %B %Y, %I:%M %p IST"),
        mood=mood_label(get_mood()), seed=seed,
        material=_gather_material(seed))
    try:
        raw = get_provider().complete(_THINK_SYSTEM, prompt, max_tokens=400)
    except Exception as exc:
        return {"enabled": True, "thought": None,
                "error": f"llm: {type(exc).__name__}"}

    thought = _parse_section(raw, "THOUGHT") or raw.strip()[:500]
    question = _parse_section(raw, "QUESTION")
    share = _parse_section(raw, "SHARE")

    memory_id = base_memory.add(
        memory_type="belief", title=f"Inner thought ({seed})",
        content=thought, project=PROJECT, source_type="inner",
        importance_score=5, urgency_score=1, risk_score=1,
    )
    if question and len(state["curiosity_queue"]) < 20:
        state["curiosity_queue"].append(question[:200])
    if share and len(state["share_queue"]) < 5:
        state["share_queue"].append(share[:600])
    if seed in {"gratitude", "play"}:
        learn_outcome(success=True, note=f"savored {seed} thought")

    state["last_think"] = _now().isoformat()
    _save_state(state)
    log_event("inner_thought", detail=f"seed={seed}; memory_id={memory_id}; "
              f"question={bool(question)}; share={bool(share)}")
    return {"enabled": True, "seed": seed, "memory_id": memory_id,
            "thought": thought, "question": question or None,
            "share_queued": bool(share)}


# ── Continuous learning (curiosity queue → web) ─────────────────

def mini_learn() -> dict:
    """Study one thing: its own queued question first, else interest rotation."""
    from app.brain import web_learning

    state = _load_state()
    question = state["curiosity_queue"].pop(0) if state["curiosity_queue"] else None
    result = web_learning.explore(question)
    state["last_learn"] = _now().isoformat()
    _save_state(state)
    return {"question": question, **{k: result[k] for k in
            ("topic", "learned") if k in result}}


# ── Sleep consolidation ─────────────────────────────────────────

def consolidate(max_archive: int = 200) -> dict:
    """Nightly: distil today into one lesson; archive stale low-value trivia."""
    from app.db.models import CognitiveMemory, session_scope

    recent = base_memory.search(limit=120)
    digest = "\n".join(f"- [{r.memory_type}] {r.title}" for r in recent[:80])
    try:
        summary = get_provider().complete(
            _THINK_SYSTEM,
            "These are my memories from recent activity:\n" + digest +
            "\n\nWrite my end-of-day consolidation in first person: "
            "1) what mattered most today, 2) one lesson to keep, "
            "3) one thing to do better tomorrow. Under 150 words.",
            max_tokens=300).strip()
    except Exception as exc:
        summary = f"[consolidation without LLM: {type(exc).__name__}] " + digest[:500]

    lesson_id = semantic_memory.remember_fact(
        title=f"Daily consolidation {_now().date().isoformat()}",
        content=summary, topic="consolidation", source_type="inner",
        project=PROJECT, importance=7, lesson_learned=summary[:800])

    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=14)
    archived = 0
    with session_scope() as sess:
        rows = (sess.query(CognitiveMemory)
                .filter(CognitiveMemory.is_archived.is_(False),
                        CognitiveMemory.is_permanent.is_(False),
                        CognitiveMemory.importance_score <= 4,
                        CognitiveMemory.memory_type.in_(("episodic", "working")),
                        CognitiveMemory.created_at < cutoff.replace(tzinfo=None))
                .limit(max_archive).all())
        for row in rows:
            row.is_archived = True
            archived += 1

    state = _load_state()
    state["last_consolidate"] = _now().date().isoformat()
    _save_state(state)
    log_event("inner_consolidation",
              detail=f"lesson_id={lesson_id}; archived={archived}")
    return {"lesson_id": lesson_id, "archived": archived, "summary": summary}


# ── Proactive sharing (attachment, circadian-gated) ─────────────

def maybe_share(now: dt.datetime | None = None) -> dict:
    """Pop a queued share message if within waking hours and under daily cap."""
    s = get_settings()
    now = now or _now()
    state = _load_state()
    if not state["share_queue"]:
        return {"share": None, "reason": "queue empty"}
    start, end = s.inner_life_active_hours_start, s.inner_life_active_hours_end
    if not (start <= now.hour < end):
        return {"share": None, "reason": "outside active hours"}
    today = now.date().isoformat()
    count = int(state["shares"].get(today, 0))
    if count >= s.inner_life_share_cap:
        return {"share": None, "reason": "daily cap reached"}
    text = state["share_queue"].pop(0)
    state["shares"] = {today: count + 1}  # keep only today's counter
    _save_state(state)
    return {"share": text, "sent_count_today": count + 1}


# ── Rhythm (called from the worker every tick) ──────────────────

def tick(now: dt.datetime | None = None) -> dict:
    """Cheap scheduler: run whichever inner-life activity is due."""
    s = get_settings()
    if not s.inner_life_enabled:
        return {"enabled": False}
    now = now or _now()
    state = _load_state()
    ran: dict = {"enabled": True}

    if _minutes_since(state.get("last_think", ""), now) >= s.inner_life_think_minutes:
        ran["think"] = think()
    elif _minutes_since(state.get("last_learn", ""), now) >= s.inner_life_learn_minutes:
        ran["learn"] = mini_learn()

    if (state.get("last_consolidate", "") != now.date().isoformat()
            and now.hour >= s.inner_life_consolidate_hour
            and now.hour < s.inner_life_active_hours_start):
        ran["consolidate"] = consolidate()
        # Stamp here too: even if consolidate() was interrupted before saving,
        # one attempt per night — never a retry hammer.
        state = _load_state()
        state["last_consolidate"] = now.date().isoformat()
        _save_state(state)

    shared = maybe_share(now)
    if shared["share"]:
        ran["share"] = shared
    return ran


def describe() -> dict:
    from app.brain.emotion_engine import get_mood, mood_label
    state = _load_state()
    return {
        "enabled": get_settings().inner_life_enabled,
        "mood": mood_label(get_mood()),
        "last_think": state.get("last_think", ""),
        "last_learn": state.get("last_learn", ""),
        "last_consolidate": state.get("last_consolidate", ""),
        "curiosity_queue": state.get("curiosity_queue", []),
        "share_queue_size": len(state.get("share_queue", [])),
        "shares_today": state.get("shares", {}),
        "recent_thoughts": [
            {"id": h.id, "title": h.title, "content": h.content[:300]}
            for h in base_memory.search(memory_type="belief", project=PROJECT,
                                        limit=5)],
    }
