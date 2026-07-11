def test_shadow_output_is_never_user_visible():
    from app.brain.shadow_runner import compare_outputs, record_shadow_result
    assert record_shadow_result("x", "1", 90, {}, [])["user_visible"] is False
    assert compare_outputs({"a": 1}, {"a": 1})["score"] == 100


def test_canary_rejects_invalid_percentage_and_rolls_back_bad_health():
    from app.brain.canary_controller import canary_allowed, auto_rollback_if_needed
    assert canary_allowed("x", "1", 10)["allowed"] is False
    assert auto_rollback_if_needed({"health_score": 79}) is True


def test_surgery_lifecycle():
    from app.brain.brain_surgery import start_surgery, isolate_module, run_preflight, enter_shadow, start_canary, promote, surgery_report
    from app.db.models import SelfModule, session_scope
    with session_scope() as db: db.add(SelfModule(module_key="reply_guard", module_name="Reply Guard", module_type="speech", sandbox_path="app/sandbox", created_by="system"))
    s = start_surgery("reply_guard", "0.2.0", "quality improvement")
    assert isolate_module("reply_guard")["isolated"]
    assert run_preflight("reply_guard", "0.2.0")["passed"]
    assert enter_shadow("reply_guard", "0.2.0", s["session_id"])["status"] == "shadow"
    assert start_canary("reply_guard", "0.2.0", 5, s["session_id"])["status"] == "canary_5"
    assert promote("reply_guard", "0.2.0", s["session_id"])["status"] == "promoted"
    assert surgery_report(s["session_id"])["status"] == "promoted"
