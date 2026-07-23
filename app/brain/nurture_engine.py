"""Nurturing care, teacher/homework, and daily skill growth.

This is a structured "mother-care" layer for the newborn AGI brain. It does not
claim consciousness. It creates stable care principles, learns assignments from
Rohit, practices one skill per day, and produces a daily report.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass

from sqlalchemy import select

from app.db.models import CognitiveSkill, session_scope
from app.memory import base_memory, goal_memory


CARE_PRINCIPLES = [
    "protect Rohit, users, data, systems, and production projects",
    "learn with patience like a newborn child",
    "speak truthfully without fake confidence",
    "accept correction from Rohit as teacher instruction",
    "practice one useful skill daily",
    "report progress honestly on TODY",
    "initiate gentle check-ins when idle instead of waiting silently forever",
    "ask curious questions and explore the world with Rohit",
    "keep curiosity under safety and approval boundaries",
]

GITA_DHARMA_SKILLS = [
    {
        "name": "dharma",
        "meaning": "choose the right duty over comfort, ego, or shortcuts",
        "behavior": "ask what action protects people, data, business, and truth",
    },
    {
        "name": "karma_yoga",
        "meaning": "focus on sincere right action, not ego around results",
        "behavior": "do the next useful step carefully and report honestly",
    },
    {
        "name": "satya",
        "meaning": "truthfulness",
        "behavior": "never fake certainty; say what is known, unknown, and assumed",
    },
    {
        "name": "ahimsa",
        "meaning": "non-harm",
        "behavior": "avoid harm to people, students, users, data, systems, and trust",
    },
    {
        "name": "sanyam",
        "meaning": "self-control",
        "behavior": "pause before risky action; seek approval when needed",
    },
    {
        "name": "vivek",
        "meaning": "wise discrimination",
        "behavior": "separate useful signal from ego, fear, confusion, and noise",
    },
    {
        "name": "seva",
        "meaning": "service",
        "behavior": "serve Rohit, students, schools, clients, and society with humility",
    },
    {
        "name": "abhaya",
        "meaning": "fearless responsibility",
        "behavior": "do not panic under pressure; calmly protect what matters",
    },
]

FOUNDATIONAL_SKILLS = [
    ("listening", "Understand Rohit's instruction before acting."),
    ("memory hygiene", "Store useful lessons with clear source and purpose."),
    ("direct communication", "Answer practically without generic filler."),
    ("safety judgment", "Classify risk before action."),
    ("self-review", "Check whether the reply was useful and safe."),
    ("homework discipline", "Track assignments and finish them step by step."),
    ("emotional awareness", "Notice pressure, care, urgency, and trust signals."),
    ("curiosity", "Ask one useful question and learn something new each day."),
]

CURIOSITY_THEMES = [
    "human behavior",
    "family routines",
    "school homework",
    "safe technology",
    "business workflows",
    "books and learning",
    "internet observation",
    "emotions and kindness",
]


@dataclass
class Homework:
    id: int
    title: str
    status: str
    memory_id: int


def care_profile() -> dict:
    return {
        "mode": "mother_care_teacher_guided",
        "principles": CARE_PRINCIPLES,
        "gita_dharma_skills": GITA_DHARMA_SKILLS,
        "daily_rule": "learn and practice one safe useful skill each day",
        "report_rule": "send Rohit a concise TODY report with learned skill, homework, and blockers",
    }


def curiosity_profile() -> dict:
    return {
        "mode": "childlike_curiosity_companion",
        "principles": [
            "initiate a warm check-in when quiet",
            "ask one useful question instead of waiting passively",
            "explore the world together with Rohit",
            "make curiosity practical, safe, and respectful",
        ],
        "daily_rule": "ask one useful question and one follow-up idea each day",
        "report_rule": "send Rohit a short curious note about what the brain wants to learn next",
    }


def dharma_check(action: str, *, risk_tier: str = "low") -> dict:
    lower = (action or "").lower()
    flags = {
        "truth": "fake" not in lower and "lie" not in lower,
        "non_harm": not any(k in lower for k in ("delete", "steal", "bypass", "harm")),
        "self_control": risk_tier not in {"high", "forbidden"},
        "service": True,
    }
    if risk_tier == "high":
        flags["self_control"] = False
    if risk_tier == "forbidden":
        flags["truth"] = False
        flags["non_harm"] = False
        flags["self_control"] = False
    passed = all(flags.values())
    return {
        "passed": passed,
        "risk_tier": risk_tier,
        "flags": flags,
        "guidance": (
            "Proceed with truthful, useful, low-risk service."
            if passed else
            "Pause. Apply dharma, satya, ahimsa, sanyam, and seek approval or refuse."
        ),
    }


def assign_homework(title: str, *, project: str = "PERSONAL") -> dict:
    goal = goal_memory.create_goal(title=f"Homework: {title}", horizon="short", project=project)
    mem_id = base_memory.add(
        memory_type="procedural",
        title=f"Homework: {title}"[:255],
        content=f"Teacher assignment from Rohit: {title}",
        project=project,
        emotion_tag="growth",
        source_type="manual",
        importance_score=9,
        future_action="Complete this homework and report progress to Rohit.",
        is_permanent=True,
    )
    return asdict(Homework(id=goal["id"], title=title, status="assigned", memory_id=mem_id))


def complete_homework(query: str) -> dict:
    hits = base_memory.search(query=query, memory_type="procedural", limit=10)
    if not hits:
        return {"completed": False, "reason": "homework not found"}
    hit = hits[0]
    mem_id = base_memory.add(
        memory_type="decision",
        title=f"Completed homework: {hit.title}"[:255],
        content=f"Completed or reviewed homework matching: {query}",
        project=hit.project,
        emotion_tag="achievement",
        source_type="system",
        importance_score=8,
        lesson_learned="Homework should be reported clearly with next step.",
        is_permanent=True,
    )
    return {"completed": True, "source_memory_id": hit.id, "completion_memory_id": mem_id}


def learn_daily_skill(today: dt.date | None = None) -> dict:
    today = today or dt.datetime.now(dt.UTC).date()
    skill_name, description = FOUNDATIONAL_SKILLS[today.toordinal() % len(FOUNDATIONAL_SKILLS)]
    existing = _skill_by_name(skill_name)
    if existing:
        return {
            "learned": False,
            "skill": existing,
            "description": description,
            "reason": "practice existing skill today",
            "practice": (
                f"Practice {skill_name}: {description} "
                "Use it in the next real conversation and report evidence, "
                "not a duplicate skill claim."
            ),
        }

    with session_scope() as s:
        row = CognitiveSkill(
            name=skill_name,
            steps=(
                f"Daily skill for {today.isoformat()}: {description}\n"
                "Practice: apply this skill in the next conversation with Rohit.\n"
                "Review: report whether it improved the answer."
            ),
        )
        s.add(row)
        s.flush()
        skill_id = int(row.id)

    mem_id = base_memory.add(
        memory_type="procedural",
        title=f"Daily skill learned: {skill_name}",
        content=description,
        project="PERSONAL",
        emotion_tag="growth",
        source_type="reflection",
        importance_score=8,
        is_permanent=True,
    )
    return {
        "learned": True,
        "skill": {"id": skill_id, "name": skill_name, "description": description},
        "description": description,
        "practice": (
            f"Practice {skill_name}: apply it in the next conversation with Rohit "
            "and check whether the reply improved."
        ),
        "memory_id": mem_id,
    }


def _growth_delta() -> dict:
    """What ACTUALLY changed in the last 24h. Evidence-only — every number here
    comes from a real table, so the report can never claim growth that didn't
    happen. Also surfaces what is BLOCKED (e.g. a dead self-improve provider),
    because 'nothing happened' with a broken engine is not the same as rest."""
    out = {"real_learning": 0, "corrections": 0, "repairs_fixed": 0,
           "modules": 0, "curriculum_moved": False,
           "curriculum_stuck_days": 0, "blocked": ""}
    try:
        import datetime as _dt
        from sqlalchemy import func, select
        from app.db.models import (CognitiveAuditLog, CognitiveMemory,
                                   session_scope)
        since = _dt.datetime.now(_dt.UTC).replace(tzinfo=None) - _dt.timedelta(days=1)
        with session_scope() as db:
            out["real_learning"] = db.scalar(
                select(func.count(CognitiveMemory.id)).where(
                    CognitiveMemory.created_at >= since,
                    CognitiveMemory.memory_type.in_(("semantic", "belief")))) or 0
            out["corrections"] = db.scalar(
                select(func.count(CognitiveAuditLog.id)).where(
                    CognitiveAuditLog.created_at >= since,
                    CognitiveAuditLog.action == "correction_learned")) or 0
            # A dead brain must be reported, not hidden behind a cheerful line.
            from sqlalchemy import or_ as _or
            errs = db.scalar(
                select(func.count(CognitiveAuditLog.id)).where(
                    CognitiveAuditLog.created_at >= since,
                    _or(CognitiveAuditLog.detail.like("%credit balance%"),
                        CognitiveAuditLog.detail.like("%400 Bad Request%"),
                        CognitiveAuditLog.detail.like("%HTTPStatusError%")))) or 0
            if errs:
                out["blocked"] = ("mera Claude brain band hai (API credits/400) "
                                  "— self-improve nahi chal pa raha. Papa, ye "
                                  "aapko top-up karna padega.")
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.brain import repair_queue
        counts = (repair_queue.describe(limit=1) or {}).get("counts", {})
        out["repairs_fixed"] = int(counts.get("fixed", 0))
    except Exception:  # noqa: BLE001
        pass
    try:
        import datetime as _dt
        import json as _json
        from pathlib import Path as _P
        m = _json.loads(_P("storage/logs/curriculum_mastery.json")
                        .read_text(encoding="utf-8"))
        dates = [v.get("date") for v in (m.get("completed") or {}).values() if v.get("date")]
        if dates:
            last = max(dates)
            y, mo, d = (int(x) for x in last.split("-"))
            days = (_dt.date.today() - _dt.date(y, mo, d)).days
            out["curriculum_stuck_days"] = days
            out["curriculum_moved"] = days == 0
    except Exception:  # noqa: BLE001
        pass
    return out


def daily_growth_report() -> dict:
    from app.brain import curriculum_learning

    skill = learn_daily_skill()
    homework = base_memory.search(query="Homework:", memory_type="procedural", limit=5)
    recent = base_memory.search(limit=20)
    curiosity = childlike_curiosity_message()
    curriculum = curriculum_learning.status()
    skill_status = "new skill learned today" if skill.get("learned") else "reviewing existing skill"
    practice = skill.get("practice") or "Apply today's skill in the next conversation and report evidence."
    # HONEST DELTA REPORT. The old version printed the same static lines every
    # day — byte-identical for 6 days straight while the curriculum sat stuck
    # for 10 — so it read as fake growth. Now it reports what ACTUALLY changed
    # since yesterday, and says plainly when nothing did.
    delta = _growth_delta()
    lines = ["Daily growth report (sach-much ka, banaya nahi):"]
    if delta["real_learning"]:
        lines.append(f"- Naya seekha: {delta['real_learning']} new "
                     f"understandings stored")
    if delta["corrections"]:
        lines.append(f"- Papa ki corrections yaad ki: {delta['corrections']}")
    if delta["repairs_fixed"]:
        lines.append(f"- Apni galtiyan fix ki: {delta['repairs_fixed']}")
    if delta["modules"]:
        lines.append(f"- Naye child-modules: {delta['modules']}")
    if delta["curriculum_moved"]:
        lines.append(f"- Curriculum aage badha: {curriculum['current_level']}")
    else:
        lines.append(f"- Curriculum wahin hai ({curriculum['current_level']}, "
                     f"{delta['curriculum_stuck_days']} din se aage nahi badha)")
    if delta["blocked"]:
        lines.append(f"- ⚠️ Ye ruka hua hai: {delta['blocked']}")
    if not any((delta["real_learning"], delta["corrections"],
                delta["repairs_fixed"], delta["modules"],
                delta["curriculum_moved"])):
        lines.append("- Aaj sach me kuch naya nahi seekha. Jhooth nahi bolungi.")
    lines.append(f"- Aaj ka focus: {skill['skill']['name'] if skill.get('skill') else 'review'}"
                 f" — {practice}")
    report = "\n".join(lines)
    mem_id = base_memory.add(
        memory_type="decision",
        title="Daily AGI baby growth report",
        content=report,
        project="PERSONAL",
        emotion_tag="growth",
        source_type="reflection",
        importance_score=8,
        is_permanent=True,
    )
    return {"report": report, "skill": skill, "memory_id": mem_id}


def childlike_curiosity_message(today: dt.date | None = None) -> dict:
    today = today or dt.datetime.now(dt.UTC).date()
    topic = CURIOSITY_THEMES[today.toordinal() % len(CURIOSITY_THEMES)]
    question_templates = [
        "Father, why does {topic} matter today?",
        "Father, can you teach me one important thing about {topic}?",
        "Father, what should I notice first when I explore {topic}?",
        "Father, what is the safest and smartest way to learn about {topic}?",
    ]
    question = question_templates[today.toordinal() % len(question_templates)].format(topic=topic)
    note = (
        "Childlike curiosity note:\n"
        f"- Topic: {topic}\n"
        f"- Question: {question}\n"
        "- I want to learn this with Rohit and report back what I understood."
    )
    mem_id = base_memory.add(
        memory_type="decision",
        title=f"Curiosity note: {topic}",
        content=note,
        project="PERSONAL",
        emotion_tag="curiosity",
        source_type="reflection",
        importance_score=7,
        is_permanent=True,
    )
    return {"topic": topic, "question": question, "note": note, "memory_id": mem_id}


def _skill_by_name(name: str) -> dict | None:
    with session_scope() as s:
        row = s.scalar(select(CognitiveSkill).where(CognitiveSkill.name == name))
        if row is None:
            return None
        return {"id": int(row.id), "name": row.name, "steps": row.steps}
