# Shree Individual TODY Chat Capabilities

The TODY adapter now covers the individual-chat API surface: conversations and archived conversations, message history/polling, text replies, threaded replies, attachments, image inspection, forwarding, editing, deletion, delivery/read receipts, message info, reactions, stars, typing, mute/archive/pin, disappearing messages, scheduling, search, link previews, view-once media, and direct/secret/group conversation creation.

Outbound side effects remain approval-gated. Destructive operations (delete, clear, disappearing settings), secret chats, forwarding, and scheduled sends must not be invoked from free-form model text without a structured command and guardian approval. Image analysis is disabled by default; when enabled it downloads only allow-listed TODY media, enforces a byte limit, and returns an explicit unavailable result when no vision provider is configured.

Phase 0 CEO task power adds normal-user task-management access through
`app/agents/tody_task_actions.py`: explicit task creation, task list reads,
task comments, and status updates. The live chat-tachy backend currently has no
watcher table/API, so Shree attaches Rohit as a group-task assignee when
`TODY_TASK_ROHIT_USER_ID` is configured. Personal tasks cannot force-watch
Rohit because chat-tachy ignores assignees for personal tasks. See
`docs/TODY_CEO_PHASE0_TASKS_MICROBLOG.md`.
