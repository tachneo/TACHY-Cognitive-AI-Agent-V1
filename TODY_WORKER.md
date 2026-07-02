# TODY Conversation Worker Design

Phase 1K adds a safe worker design and dry-run function only. It does not
install cron, systemd, supervisor, queue workers, or live background polling.

## Safety Rules

1. Polling is read-only until a message is selected for supervised processing.
2. One message is processed at a time.
3. Every inbound message must have or derive a stable `message_id`.
4. Already-processed `message_id` values are rejected before drafting.
5. Non-guardian replies are always approval-gated.
6. Guardian direct reply is only allowed after trusted Rohit identity matches.
7. `TODY_SUPERVISED_AUTO_REPLY=false` by default.
8. Worker state must be observable through an authenticated status endpoint.

## Dry-Run Flow

```text
manual/API trigger
-> acquire in-process worker lock
-> read recent conversations
-> choose one conversation
-> read recent messages
-> select latest unprocessed text message
-> if dry_run=true: report candidate only
-> if dry_run=false: process through existing TODY reply pipeline
-> release lock
-> write audit event
```

## Activation Rule

Do not activate a real background worker until Rohit explicitly approves:

```text
Do you approve enabling the TODY worker process for maa.tachy.in?
```

Until then, use `POST /tody/worker/dry-run` manually.

## Manual Activation Commands

All commands require the protected API key.

Read-only config preflight, no TODY network login:

```bash
curl -H "X-API-Key: $INTERNAL_API_KEY" \
  "http://127.0.0.1:8200/tody/activate/preflight"
```

Optional login check:

```bash
curl -H "X-API-Key: $INTERNAL_API_KEY" \
  "http://127.0.0.1:8200/tody/activate/preflight?check_login=true"
```

Find one candidate only; no draft and no send:

```bash
curl -X POST -H "X-API-Key: $INTERNAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true, "conversation_limit": 10, "message_limit": 10}' \
  "http://127.0.0.1:8200/tody/activate/process-one"
```

Process exactly one message through the supervised pipeline:

```bash
curl -X POST -H "X-API-Key: $INTERNAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false, "conversation_limit": 10, "message_limit": 10}' \
  "http://127.0.0.1:8200/tody/activate/process-one"
```

## Disabled Service Template

Do not install or enable this until Rohit approves.

```ini
[Unit]
Description=TACHY TODY Conversation Worker
After=network.target

[Service]
WorkingDirectory=/var/www/maa.tachy.in
EnvironmentFile=/var/www/maa.tachy.in/.env
ExecStart=/var/www/maa.tachy.in/.venv/bin/python -m app.scripts.tody_worker_loop
Restart=always
RestartSec=10
User=www-data
Group=www-data

[Install]
WantedBy=multi-user.target
```

The loop script exists at `app/scripts/tody_worker_loop.py`, but refuses live
mode unless `TODY_WORKER_LIVE_CONFIRM=YES` is set.
