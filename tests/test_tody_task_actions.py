from __future__ import annotations


def _clear_settings():
    from app.config import get_settings
    get_settings.cache_clear()


def test_task_command_parser_create_comment_status_list():
    from app.agents import tody_task_actions as tasks

    create = tasks.parse_command(
        "create task: Fix login | priority: high | due: 2026-08-01 | group: 12 | assignees: 7,8"
    )
    assert create["action"] == "create"
    assert create["title"] == "Fix login"
    assert create["priority"] == "high"
    assert create["deadline"] == "2026-08-01"
    assert create["group_id"] == 12
    assert create["assignee_ids"] == [7, 8]

    comment = tasks.parse_command("comment task #42: QA complete")
    assert comment == {"action": "comment", "task_id": 42, "body": "QA complete"}

    status = tasks.parse_command("mark task #42 as in progress: checking production")
    assert status == {
        "action": "status",
        "task_id": 42,
        "status": "in_progress",
        "notes": "checking production",
    }
    assert tasks.parse_command("list tasks") == {"action": "list"}


def test_task_parser_does_not_convert_plain_work_into_task():
    from app.agents import tody_task_actions as tasks

    assert tasks.parse_command("complete the pending task") is None
    assert tasks.parse_command("please check production and guide me") is None


def test_prepare_create_forces_rohit_participant_for_group_task(monkeypatch):
    monkeypatch.setenv("TODY_TASK_DEFAULT_GROUP_ID", "91")
    monkeypatch.setenv("TODY_TASK_ROHIT_USER_ID", "11")
    monkeypatch.setenv("TODY_TASK_FORCE_ROHIT_WATCHER", "true")
    _clear_settings()

    from app.agents import tody_task_actions as tasks

    out = tasks.prepare_create_payload({
        "title": "Daily SEO review",
        "priority": "urgent",
        "assignee_ids": [3, 11],
    })

    assert out["group_id"] == 91
    assert out["assignee_ids"] == [3, 11]
    assert out["watcher_mode"] == "assignee_until_chat_tachy_watcher_api_exists"
    assert out["watcher_warning"] is None


def test_prepare_create_warns_when_personal_task_cannot_add_watcher(monkeypatch):
    monkeypatch.setenv("TODY_TASK_DEFAULT_GROUP_ID", "0")
    monkeypatch.setenv("TODY_TASK_ROHIT_USER_ID", "11")
    _clear_settings()

    from app.agents import tody_task_actions as tasks

    out = tasks.prepare_create_payload({"title": "Personal-only task"})
    assert out["group_id"] is None
    assert "personal tasks ignore assignees" in out["watcher_warning"]


def test_create_task_uses_normal_user_api_payload(monkeypatch):
    monkeypatch.setenv("TODY_TASKS_ENABLED", "true")
    monkeypatch.setenv("TODY_TASK_DEFAULT_GROUP_ID", "9")
    monkeypatch.setenv("TODY_TASK_ROHIT_USER_ID", "4")
    _clear_settings()

    from app.agents import tody_task_actions as tasks

    calls = []

    class FakeClient:
        def create_task(self, **payload):
            calls.append(payload)
            return {"task": {"id": 77, "title": payload["title"]}}

    monkeypatch.setattr(tasks, "get_client", lambda: FakeClient())
    out = tasks.do_create_task({"title": "Build CEO dashboard", "assignee_ids": [2]})

    assert out["ok"] is True
    assert calls == [{
        "title": "Build CEO dashboard",
        "description": None,
        "deadline": None,
        "priority": "medium",
        "group_id": 9,
        "assignee_ids": [2, 4],
    }]


def test_tody_task_action_registered_as_high_risk():
    from app.brain import action_engine

    names = {s["name"] for s in action_engine.registry()}
    assert {"tody_create_task", "tody_task_comment", "tody_task_status"} <= names
    assert action_engine.REGISTRY["tody_create_task"].risk_tier == "high"


def test_guardian_task_command_disabled_by_default(monkeypatch):
    monkeypatch.setenv("TODY_TASKS_ENABLED", "false")
    _clear_settings()

    from app.agents import tody_agent

    out = tody_agent._guardian_command_reply("create task: fix task API")
    assert "disabled" in out


def test_guardian_task_command_queues_approval(monkeypatch):
    monkeypatch.setenv("TODY_TASKS_ENABLED", "true")
    monkeypatch.setenv("TODY_TASK_DEFAULT_GROUP_ID", "5")
    monkeypatch.setenv("TODY_TASK_ROHIT_USER_ID", "2")
    monkeypatch.setenv("TODY_TASK_AUTONOMOUS_CREATE", "false")
    _clear_settings()

    from app.agents import tody_agent

    out = tody_agent._guardian_command_reply("create task: Check SEO report | priority: high")
    assert "Ready to create TODY task" in out
    assert "approve" in out


def test_guardian_task_command_can_execute_when_autonomous_enabled(monkeypatch):
    monkeypatch.setenv("TODY_TASKS_ENABLED", "true")
    monkeypatch.setenv("TODY_TASK_AUTONOMOUS_CREATE", "true")
    monkeypatch.setenv("TODY_TASK_DEFAULT_GROUP_ID", "5")
    monkeypatch.setenv("TODY_TASK_ROHIT_USER_ID", "2")
    _clear_settings()

    from app.agents import tody_agent

    calls = []

    class FakeClient:
        def create_task(self, **payload):
            calls.append(payload)
            return {"task": {"id": 88, "title": payload["title"]}}

    monkeypatch.setattr(tody_task_actions := __import__(
        "app.agents.tody_task_actions", fromlist=["get_client"]
    ), "get_client", lambda: FakeClient())

    out = tody_agent._guardian_command_reply("create task: Review growth plan")
    assert "TODY task bana diya #88" in out
    assert calls[0]["assignee_ids"] == [2]
