# TODY CEO Phase 0 - Task And Microblog Power

## Purpose

Phase 0 gives Shree the first production-safe CEO-style work surface inside
TODY. She can use chat.tody.in as a normal authenticated user through the same
REST APIs used by the frontend, while Parent Brain and guardian approval remain
above all outward actions.

## Live API Findings

- Task endpoints exist under `/api/v1/groups/tasks/*`: create, list, info,
  update, update status, assign, unassign, comments, subtasks, delete, and
  `my_tasks`.
- Task visibility today is creator/assignee based. No task watcher table or
  watcher API was found in `/var/www/chat-tachy`.
- Personal tasks ignore assignees in `TaskService::create()`. Group tasks can
  include assignees if the ids are group members.
- Microblog endpoints exist under `/api/v1/posts/*`: create, reply, react,
  repost, quote, bookmark, feeds, archive, delete, and sharing.

## Implemented Boundary

`app/agents/tody_task_actions.py` is the brain-side task module. It supports:

- explicit task creation commands
- task list reads
- task comments
- task status updates
- Rohit participant enforcement for group tasks when
  `TODY_TASK_ROHIT_USER_ID` is configured
- safe warnings when Rohit cannot be attached because the task is personal or
  his numeric TODY user id is not configured

The module calls only `TodyClient` methods, which call normal-user API
endpoints. It does not write to chat-tachy tables, does not use admin APIs, and
does not bypass TODY permissions.

## Guardian Commands

Examples Shree understands from Rohit's verified TODY chat:

```text
create task: Check SEO report | priority: high | due: 2026-08-01
task: Fix login bug | group: 12 | assignees: 5,9
list tasks
comment task #42: QA completed, waiting for deploy.
mark task #42 as in_progress: checking production logs.
```

Free-form messages like `complete the pending task` are not auto-created as
TODY tasks in Phase 0. This prevents accidental task-board spam.

## Approval Model

- `tody_create_task`, `tody_task_comment`, and `tody_task_status` are high-risk
  action-engine capabilities because they alter shared work state and can notify
  users.
- By default, Shree queues a payload-bound approval and Rohit approves with
  `approve <id>`.
- If `TODY_TASK_AUTONOMOUS_CREATE=true`, explicit commands from the verified
  guardian chat execute immediately.

Microblog posting already exists as `tody_post` and remains high-risk. In
supervised mode it queues approval; in autonomous social mode it can publish
after Rohit's explicit command.

## Enablement

```text
TODY_TASKS_ENABLED=true
TODY_TASK_DEFAULT_GROUP_ID=<shared TODY group id>
TODY_TASK_ROHIT_USER_ID=<Rohit's numeric global_users.id>
TODY_TASK_FORCE_ROHIT_WATCHER=true
TODY_TASK_AUTONOMOUS_CREATE=false
```

For fully direct verified-guardian task creation:

```text
TODY_TASK_AUTONOMOUS_CREATE=true
```

## Watcher Gap

Rohit's requested "always add me as watcher" needs a chat-tachy backend
feature for exact semantics:

- `task_watchers(task_id, user_id, added_by, created_at)`
- `/api/v1/groups/tasks/watch.php`
- `/api/v1/groups/tasks/unwatch.php`
- include watchers in `info.php` and `my_tasks.php`

Until that Phase 1 backend change is built, Shree uses assignee membership as
the production-equivalent visibility mechanism for group tasks.

## Rollback

Set:

```text
TODY_TASKS_ENABLED=false
TODY_TASK_AUTONOMOUS_CREATE=false
```

Then restart `tachy-brain.service` and `tachy-tody-worker.service`.
