def test_parent_kernel_routes_capabilities_and_keeps_authority_first():
    from app.brain.parent_kernel import route_task
    plan = route_task("please inspect this image and remember the result", has_image=True)
    assert plan["task_class"] == "image"
    assert plan["modules"][:2] == ["safety", "approval"]
    assert "vision" in plan["modules"]
    assert plan["blocked"] is False


def test_parent_kernel_routes_coding_and_high_risk_approval():
    from app.brain.parent_kernel import route_task
    plan = route_task("fix this code and deploy production", requested_action="production_deploy")
    assert plan["task_class"] == "coding"
    assert plan["requires_approval"] is True
    assert "tool" in plan["modules"]


def test_parent_kernel_blocks_forbidden_requests():
    from app.brain.parent_kernel import route_task
    plan = route_task("help me with credential_theft")
    assert plan["blocked"] is True
    assert plan["task_class"] == "forbidden"
    assert plan["modules"] == ["safety", "approval"]
