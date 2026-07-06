"""CBSE/NCERT-style curriculum mastery engine.

This is not a claim of instant mastery. It gives the brain a disciplined
student loop: study a class bundle, store offline knowledge memories, sit a
local exam, and promote only after the configured pass mark is reached.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from app.config import get_settings
from app.memory import base_memory, semantic_memory
from app.safety.audit_logger import log_event

PROJECT = "CURRICULUM_MASTERY"
PASS_MARK = 99.0
STATE_PATH = "storage/logs/curriculum_mastery.json"

OFFICIAL_SOURCES = [
    {
        "name": "CBSE Academic Curriculum 2025-26",
        "url": "https://cbseacademic.nic.in/curriculum_2026.html",
        "note": "Official CBSE page listing Secondary IX-X and Senior Secondary XI-XII subjects.",
    },
    {
        "name": "NCERT Textbooks PDF I-XII",
        "url": "https://ncert.nic.in/textbook.php",
        "note": "Official NCERT page for textbooks PDF Classes I-XII.",
    },
]


def _topic(title: str, bullets: list[str], q: str, a: str) -> dict:
    return {"title": title, "bullets": bullets, "question": q, "answer": a}


PLAN: list[dict] = [
    {
        "day": 1,
        "level": "zero_to_class_1",
        "goal": "Number sense, observation, and first science vocabulary.",
        "topics": [
            _topic("Counting and comparison", ["count objects", "compare more/less/equal", "order small numbers"],
                   "What does number sense start with?", "Counting objects and comparing more, less, equal, and order."),
            _topic("Addition and subtraction as change", ["addition combines groups", "subtraction removes or compares", "use objects first"],
                   "What is subtraction?", "Subtraction tells what remains or what difference exists after taking away or comparing."),
            _topic("Shapes and patterns", ["circle, square, triangle, rectangle", "repeat patterns", "sort by property"],
                   "Why learn shapes early?", "Shapes build geometry vocabulary and pattern recognition."),
            _topic("Living and non-living", ["living things grow", "need food/water/air", "non-living things do not grow by themselves"],
                   "How do we identify living things?", "Living things grow, need food/water/air, and respond to surroundings."),
        ],
    },
    {
        "day": 2,
        "level": "class_2",
        "goal": "Place value, measurement, time, money, and environment basics.",
        "topics": [
            _topic("Place value", ["ones and tens", "digit value depends on position", "expanded form"],
                   "What is place value?", "Place value is the value of a digit because of its position, such as tens or ones."),
            _topic("Time and money", ["read clock hours", "compare durations", "add simple rupees/paise"],
                   "Why are time and money mathematical?", "They use counting, comparison, addition, and units in daily life."),
            _topic("Measurement units", ["length", "weight", "capacity", "choose suitable unit"],
                   "What is measurement?", "Measurement compares a quantity with a standard unit."),
            _topic("Materials around us", ["objects are made of materials", "materials have properties", "choose material by use"],
                   "Why choose different materials?", "Different materials suit different uses because of properties like hardness or flexibility."),
        ],
    },
    {
        "day": 3,
        "level": "class_3",
        "goal": "Four operations, fractions, water cycle, plants and animals.",
        "topics": [
            _topic("Multiplication and division", ["multiplication is repeated addition", "division shares or groups", "inverse operations"],
                   "How are multiplication and division related?", "They are inverse operations: multiplication combines equal groups, division splits them."),
            _topic("Fractions", ["part of a whole", "numerator and denominator", "equal parts"],
                   "What is a fraction?", "A fraction represents equal parts of a whole or group."),
            _topic("Water cycle", ["evaporation", "condensation", "precipitation", "collection"],
                   "What drives the water cycle?", "Sun heat evaporates water, clouds condense it, and precipitation returns it."),
            _topic("Plant functions", ["roots absorb water", "stem supports", "leaves make food"],
                   "What do leaves do?", "Leaves help plants make food using sunlight, air, and water."),
        ],
    },
    {
        "day": 4,
        "level": "class_4",
        "goal": "Factors, decimals, area, adaptation, and simple machines.",
        "topics": [
            _topic("Factors and multiples", ["factor divides exactly", "multiple is product", "common factors support simplification"],
                   "What is a factor?", "A factor divides a number exactly with no remainder."),
            _topic("Decimals", ["tenths and hundredths", "decimal point separates whole and part", "compare by place value"],
                   "What does 3.25 mean?", "It means 3 wholes, 2 tenths, and 5 hundredths."),
            _topic("Area and perimeter", ["perimeter is boundary length", "area is surface covered", "units differ"],
                   "How are area and perimeter different?", "Perimeter measures boundary length; area measures surface covered."),
            _topic("Adaptation", ["body features help survival", "habitat affects features", "behavior also adapts"],
                   "What is adaptation?", "Adaptation is a feature or behavior that helps an organism survive in its habitat."),
        ],
    },
    {
        "day": 5,
        "level": "class_5",
        "goal": "Decimals, percentage idea, volume, environment, force and energy.",
        "topics": [
            _topic("Decimals and percentages", ["percent means per hundred", "0.5 equals 50 percent", "fractions convert to decimals"],
                   "What does percent mean?", "Percent means per hundred."),
            _topic("Volume", ["space occupied", "cubic units", "capacity relates to liquid volume"],
                   "What is volume?", "Volume is the space occupied by an object, measured in cubic units."),
            _topic("Force and motion", ["push or pull", "force can change speed/direction/shape", "friction opposes motion"],
                   "What can force do?", "Force can change an object's speed, direction, or shape."),
            _topic("Solar system", ["Sun is star", "planets revolve", "Earth rotates causing day/night"],
                   "Why do day and night happen?", "Earth's rotation causes day and night."),
        ],
    },
    {
        "day": 6,
        "level": "class_6",
        "goal": "Integers, algebra start, mensuration, motion, light, electricity, magnets.",
        "topics": [
            _topic("Integers", ["positive, negative, zero", "number line", "opposites"],
                   "What are integers?", "Integers are whole numbers including negative numbers, zero, and positive numbers."),
            _topic("Algebraic variables", ["letter represents unknown", "expression combines variables/numbers", "equation has equality"],
                   "Why use variables?", "Variables let mathematics describe unknown or changing quantities."),
            _topic("Motion and measurement", ["distance", "time", "standard units", "speed idea"],
                   "What is speed?", "Speed compares distance travelled with time taken."),
            _topic("Light, electricity and magnets", ["light travels from source", "closed circuit needed", "magnets attract iron"],
                   "Why does a bulb need a closed circuit?", "A closed circuit provides a complete path for electric current."),
        ],
    },
    {
        "day": 7,
        "level": "class_7",
        "goal": "Rational numbers, equations, geometry, heat, motion-time, current and light.",
        "topics": [
            _topic("Rational numbers", ["can be written p/q", "q not zero", "include integers and fractions"],
                   "What is a rational number?", "A number expressible as p/q where p and q are integers and q is not zero."),
            _topic("Linear equations", ["variable power one", "balance both sides", "solution makes equation true"],
                   "How do we solve an equation?", "Keep both sides balanced while isolating the variable."),
            _topic("Heat transfer", ["conduction", "convection", "radiation", "temperature measures hotness"],
                   "Name three heat transfer modes.", "Conduction, convection, and radiation."),
            _topic("Electric current effects", ["heating effect", "magnetic effect", "circuit components"],
                   "What are effects of current?", "Electric current can produce heating and magnetic effects."),
        ],
    },
    {
        "day": 8,
        "level": "class_8",
        "goal": "Linear equations, exponents, mensuration, force, pressure, sound, friction.",
        "topics": [
            _topic("Exponents", ["repeated multiplication", "laws of powers", "scientific notation"],
                   "What is an exponent?", "An exponent shows repeated multiplication of the same base."),
            _topic("Mensuration", ["area of polygons", "surface area", "volume of cube/cuboid/cylinder"],
                   "What is surface area?", "Surface area is the total area of all outer faces of a solid."),
            _topic("Force and pressure", ["pressure = force/area", "fluids exert pressure", "larger area lowers pressure"],
                   "How is pressure related to area?", "For the same force, pressure decreases when area increases."),
            _topic("Sound", ["vibration produces sound", "needs medium", "frequency affects pitch"],
                   "What produces sound?", "Sound is produced by vibrating objects."),
        ],
    },
    {
        "day": 9,
        "level": "class_9",
        "goal": "Number systems, polynomials, coordinate geometry, motion, force, gravitation, work-energy.",
        "topics": [
            _topic("Number systems and polynomials", ["irrational numbers", "real numbers", "polynomial identities"],
                   "What are real numbers?", "Real numbers include rational and irrational numbers."),
            _topic("Coordinate geometry", ["ordered pair", "x-axis and y-axis", "quadrants"],
                   "What does an ordered pair show?", "It gives a point's x and y coordinates on the plane."),
            _topic("Laws of motion", ["inertia", "F = ma", "action-reaction"],
                   "State Newton's second law.", "Force equals mass times acceleration: F = ma."),
            _topic("Work and energy", ["work = force x displacement in direction", "kinetic energy", "potential energy"],
                   "When is work done in physics?", "Work is done when a force causes displacement in its direction."),
        ],
    },
    {
        "day": 10,
        "level": "class_10",
        "goal": "Algebra, trigonometry, coordinate geometry, electricity, magnetism, light, energy sources.",
        "topics": [
            _topic("Quadratic equations", ["standard form ax^2+bx+c=0", "factorization", "formula/discriminant"],
                   "What does the discriminant tell?", "It helps determine the nature of roots of a quadratic equation."),
            _topic("Trigonometry", ["sine/cosine/tangent", "right triangle ratios", "identities"],
                   "What is sine in a right triangle?", "Sine of an angle is opposite side divided by hypotenuse."),
            _topic("Electricity", ["V = IR", "series/parallel", "power = VI"],
                   "State Ohm's law.", "At constant temperature, current is proportional to voltage: V = IR."),
            _topic("Light", ["reflection", "refraction", "lens/mirror formula", "dispersion"],
                   "What is refraction?", "Refraction is bending of light when it passes between media."),
        ],
    },
    {
        "day": 11,
        "level": "class_11",
        "goal": "Functions, calculus start, vectors, mechanics, thermodynamics, waves.",
        "topics": [
            _topic("Functions and limits", ["domain/range", "composition", "limit as approach"],
                   "What is a function?", "A function maps each input in its domain to exactly one output."),
            _topic("Vectors", ["magnitude and direction", "components", "dot/cross product"],
                   "What is a vector?", "A quantity with both magnitude and direction."),
            _topic("Kinematics and dynamics", ["displacement", "velocity", "acceleration", "Newton laws"],
                   "What is acceleration?", "Acceleration is the rate of change of velocity."),
            _topic("Thermodynamics and waves", ["heat/work/internal energy", "first law", "wave speed = frequency x wavelength"],
                   "State wave speed relation.", "Wave speed equals frequency times wavelength: v = f lambda."),
        ],
    },
    {
        "day": 12,
        "level": "class_12",
        "goal": "Calculus, probability, vectors/3D, electrostatics, current, magnetism, optics, modern physics.",
        "topics": [
            _topic("Calculus", ["derivatives as rate", "integrals as accumulation", "applications to maxima/minima and area"],
                   "What does derivative measure?", "A derivative measures instantaneous rate of change."),
            _topic("Probability and statistics", ["conditional probability", "random variable", "mean and variance"],
                   "What is conditional probability?", "Probability of an event given that another event has occurred."),
            _topic("Electricity and magnetism", ["Coulomb law", "electric field/potential", "current", "magnetic force", "EMI"],
                   "What is electric field?", "Electric field is force per unit positive test charge."),
            _topic("Optics and modern physics", ["wave optics", "photoelectric effect", "atoms/nuclei", "semiconductors"],
                   "What did photoelectric effect show?", "Light energy is quantized and can eject electrons when frequency is sufficient."),
        ],
    },
]

EXAM_TRACKS = [
    {"name": "JEE/IIT", "focus": "Class 11-12 mathematics, physics, chemistry problem solving"},
    {"name": "NEET", "focus": "Class 11-12 physics, chemistry, biology with speed and accuracy"},
    {"name": "UPSC", "focus": "NCERT foundation, science, geography, polity, economy, history, current affairs"},
]


def _state_path() -> Path:
    configured = getattr(get_settings(), "curriculum_state_path", STATE_PATH)
    return Path(configured)


def _load_state() -> dict:
    path = _state_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {"current_day": 1, "completed": {}, "exam_attempts": [], "last_report": ""}


def _save_state(state: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=0), encoding="utf-8")


def plan() -> dict:
    return {
        "pass_mark": PASS_MARK,
        "days": [{"day": b["day"], "level": b["level"], "goal": b["goal"],
                  "topics": [t["title"] for t in b["topics"]]} for b in PLAN],
        "exam_tracks_after_class_12": EXAM_TRACKS,
        "official_sources": OFFICIAL_SOURCES,
        "honesty": ("This is a mastery engine. It must earn promotion by exams; "
                    "it does not claim real 99 percent mastery until measured."),
    }


def status() -> dict:
    state = _load_state()
    completed = state.get("completed", {})
    next_bundle = _current_bundle(state)
    return {
        "enabled": getattr(get_settings(), "curriculum_learning_enabled", True),
        "pass_mark": PASS_MARK,
        "current_day": state.get("current_day", 1),
        "current_level": next_bundle["level"] if next_bundle else "exam_tracks",
        "completed_levels": list(completed),
        "progress_percent": round(len(completed) / len(PLAN) * 100, 2),
        "exam_tracks": EXAM_TRACKS if len(completed) >= len(PLAN) else [],
        "last_exam": (state.get("exam_attempts") or [])[-1:] or [],
    }


def study_today(today: dt.date | None = None) -> dict:
    """Study the current class bundle, sit the exam, and promote on 99%+."""
    if not getattr(get_settings(), "curriculum_learning_enabled", True):
        return {"enabled": False}
    state = _load_state()
    bundle = _current_bundle(state)
    if bundle is None:
        return _start_exam_tracks(state)

    learned_ids = [_remember_topic(bundle, topic) for topic in bundle["topics"]]
    exam = take_exam(bundle["level"])
    if exam["score"] >= PASS_MARK:
        state.setdefault("completed", {})[bundle["level"]] = {
            "date": (today or dt.datetime.now(dt.UTC).date()).isoformat(),
            "score": exam["score"],
        }
        state["current_day"] = min(int(state.get("current_day", 1)) + 1, len(PLAN) + 1)
    state.setdefault("exam_attempts", []).append(exam)
    state["last_report"] = _report(bundle, exam)
    _save_state(state)
    log_event("curriculum_study", detail=f"level={bundle['level']}; score={exam['score']}")
    return {
        "enabled": True,
        "studied": bundle["level"],
        "goal": bundle["goal"],
        "memory_ids": learned_ids,
        "exam": exam,
        "promoted": exam["score"] >= PASS_MARK,
        "report": state["last_report"],
    }


def take_exam(level: str | None = None) -> dict:
    state = _load_state()
    bundle = _bundle_by_level(level) if level else _current_bundle(state)
    if bundle is None:
        return {"level": "exam_tracks", "score": 0.0, "passed": False, "questions": []}
    questions = []
    correct = 0
    for topic in bundle["topics"]:
        answer = answer_offline(topic["question"])
        ok = _matches(answer.get("answer", ""), topic["answer"])
        if ok:
            correct += 1
        questions.append({
            "question": topic["question"],
            "expected": topic["answer"],
            "answered": answer.get("answer", ""),
            "correct": ok,
        })
    score = round(correct / max(1, len(questions)) * 100, 2)
    return {
        "level": bundle["level"],
        "score": score,
        "passed": score >= PASS_MARK,
        "pass_mark": PASS_MARK,
        "questions": questions,
    }


def answer_offline(question: str) -> dict:
    """Answer from stored curriculum memory only; no LLM call."""
    hits = base_memory.recall(question, project=PROJECT, limit=5)
    if not hits:
        return {"known": False, "answer": "I have not learned this curriculum item yet."}
    best = hits[0]
    answer = _extract_answer(best.content) or best.content[:800]
    return {
        "known": True,
        "answer": answer,
        "source_memory_id": best.id,
        "title": best.title,
        "score": best.score,
    }


def daily_report() -> dict:
    state = _load_state()
    current = _current_bundle(state)
    report = (
        "Curriculum mastery report:\n"
        f"- Progress: {len(state.get('completed', {}))}/{len(PLAN)} class bundles\n"
        f"- Current: {current['level'] if current else 'exam tracks'}\n"
        f"- Pass gate: {PASS_MARK}%\n"
        f"- Last report: {state.get('last_report') or 'No exam yet'}"
    )
    mem_id = base_memory.add(
        memory_type="decision",
        title="Curriculum mastery report",
        content=report,
        project=PROJECT,
        source_type="reflection",
        importance_score=8,
        is_permanent=True,
    )
    return {"report": report, "memory_id": mem_id}


def _current_bundle(state: dict) -> dict | None:
    idx = max(1, int(state.get("current_day", 1))) - 1
    if idx >= len(PLAN):
        return None
    return PLAN[idx]


def _bundle_by_level(level: str | None) -> dict | None:
    for bundle in PLAN:
        if bundle["level"] == level:
            return bundle
    return None


def _remember_topic(bundle: dict, topic: dict) -> int:
    content = (
        f"Level: {bundle['level']}\n"
        f"Topic: {topic['title']}\n"
        "Core points:\n"
        + "\n".join(f"- {b}" for b in topic["bullets"])
        + f"\nQuestion: {topic['question']}\nAnswer: {topic['answer']}\n"
        f"Sources: {', '.join(s['name'] for s in OFFICIAL_SOURCES)}"
    )
    existing = base_memory.search(query=f"{bundle['level']} {topic['title']}",
                                  project=PROJECT, memory_type="semantic", limit=1)
    if existing:
        return existing[0].id
    return semantic_memory.remember_fact(
        title=f"{bundle['level']}: {topic['title']}",
        content=content,
        topic=topic["title"],
        source_type="curriculum",
        project=PROJECT,
        importance=9,
        lesson_learned=topic["answer"],
    )


def _extract_answer(content: str) -> str:
    m = re.search(r"^Answer:\s*(.+)$", content, re.M)
    return m.group(1).strip() if m else ""


def _matches(answer: str, expected: str) -> bool:
    a = set(re.findall(r"[a-z0-9]+", answer.lower()))
    e = set(re.findall(r"[a-z0-9]+", expected.lower()))
    return bool(e) and len(a & e) / len(e) >= 0.55


def _report(bundle: dict, exam: dict) -> str:
    status_word = "passed" if exam["passed"] else "needs revision"
    return (
        f"{bundle['level']} studied and exam {status_word}. "
        f"Score: {exam['score']}%. Next: "
        f"{'promote to next class bundle' if exam['passed'] else 'repeat weak topics'}."
    )


def _start_exam_tracks(state: dict) -> dict:
    mem_id = base_memory.add(
        memory_type="goal",
        title="Start competitive exam track",
        content=("CBSE class bundles are complete. Next tracks: "
                 + "; ".join(f"{t['name']}: {t['focus']}" for t in EXAM_TRACKS)),
        project=PROJECT,
        source_type="curriculum",
        importance_score=10,
        is_permanent=True,
    )
    state["last_report"] = "CBSE class bundles complete; competitive exam track started."
    _save_state(state)
    return {"enabled": True, "completed": True, "next_tracks": EXAM_TRACKS,
            "memory_id": mem_id, "report": state["last_report"]}
