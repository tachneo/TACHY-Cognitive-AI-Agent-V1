"""Repair queue (Phase 3A — metacognitive loop step 2).

Evidence-tiered accumulation of Shree's own failure signatures: guardian
corrections repair immediately, conversational ground truth needs recurrence
(and ≥2 distinct strangers), system events need recurrence, LLM self-critique
NEVER repairs alone, and a signature that recurs after a fix escalates to Rohit
instead of oscillating.
"""
from app.brain import repair_queue as rq


def test_tier1_guardian_correction_ready_immediately():
    out = rq.note_failure("correction:name", tier=1, guardian=True,
                          person="Rohit Kumar", fix_class="directive")
    assert out["noted"] and out["status"] == "ready"


def test_tier2_single_stranger_never_ready_alone():
    for _ in range(4):
        out = rq.note_failure("reply-too-long", tier=2, person="komal")
    assert out["status"] == "observing"  # one annoyed user can't steer her


def test_tier2_two_distinct_strangers_become_ready():
    rq.note_failure("reply-too-long", tier=2, person="komal")
    out = rq.note_failure("reply-too-long", tier=2, person="zarathakoo")
    assert out["status"] == "ready"


def test_tier2_guardian_involvement_needs_only_recurrence():
    rq.note_failure("robotic-reply", tier=2, guardian=True, person="Rohit Kumar")
    out = rq.note_failure("robotic-reply", tier=2, guardian=True,
                          person="Rohit Kumar")
    assert out["status"] == "ready"


def test_tier3_system_event_ready_on_recurrence():
    assert rq.note_failure("worker-crash:TypeError", tier=3,
                           fix_class="code")["status"] == "observing"
    assert rq.note_failure("worker-crash:TypeError", tier=3,
                           fix_class="code")["status"] == "ready"


def test_tier4_self_critique_never_ready_alone():
    for _ in range(6):
        out = rq.note_failure("self-critique:empty-reply", tier=4)
    assert out["status"] == "observing"


def test_tier4_upgraded_by_higher_tier_corroboration():
    for _ in range(3):
        rq.note_failure("self-critique:prompt-leak", tier=4)
    # A hard system event corroborates the same signature → tier upgrades and
    # the accumulated recurrence now counts.
    out = rq.note_failure("self-critique:prompt-leak", tier=3)
    assert out["tier"] == 3 and out["status"] == "ready"


def test_fixed_signature_recurring_escalates_never_refixed():
    rq.note_failure("correction:tone", tier=1, guardian=True)
    assert rq.mark("correction:tone", status="fixed", note="directive patched")
    out = rq.note_failure("correction:tone", tier=1, guardian=True)
    assert out["status"] == "escalated"  # one-fix-per-signature, no oscillation


def test_conversational_detector_maps_complaints_to_signatures():
    noted = rq.note_conversational_signals(
        "tum itna lamba kyo likhti ho?", person="komal", conversation_id=264)
    assert noted == ["reply-too-long"]
    noted = rq.note_conversational_signals(
        "tum jawab kyo nahi de rahi ho", person="Rohit Kumar", guardian=True)
    assert noted == ["not-replying"]
    assert rq.note_conversational_signals("good morning!") == []


def test_ready_lists_strongest_evidence_first_and_scan_reads_it():
    rq.note_failure("worker-crash:KeyError", tier=3, fix_class="code")
    rq.note_failure("worker-crash:KeyError", tier=3, fix_class="code")
    rq.note_failure("correction:language", tier=1, guardian=True,
                    fix_class="directive")
    items = rq.ready()
    assert items[0]["tier"] == 1
    # self_diagnose surfaces code-class ready signatures as repair candidates.
    from app.brain import self_diagnose
    d = self_diagnose.scan()
    assert any("worker-crash:keyerror" in b for b in d["code_bugs"])
    assert any(r["signature"] == "correction:language" for r in d["behavioral"])


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("REPAIR_QUEUE_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    out = rq.note_failure("anything", tier=1, guardian=True)
    assert out == {"noted": False, "reason": "disabled"}


def test_golden_deterministic_checks_run_without_llm():
    from app.brain import golden
    case = {"name": "t", "message": "x", "max_sentences": 2,
            "forbid": ["(?i)court"],
            "criteria": ["never reached: deterministic check fails first"]}
    bad = golden.run_case(case, reply="One. Two. Three. And a court case.")
    assert not bad["passed"]
    ok = golden.run_case({"name": "t2", "message": "x", "max_sentences": 3,
                          "forbid": ["(?i)court"]},
                         reply="Chhota reply. Bas itna hi.")
    assert ok["passed"]


def test_golden_cases_file_is_valid():
    from app.brain import golden
    cases = golden.load_cases()
    names = [c["name"] for c in cases]
    assert len(names) >= 5 and len(names) == len(set(names))
    for c in cases:
        assert c.get("criteria") or c.get("forbid") or c.get("max_sentences")
