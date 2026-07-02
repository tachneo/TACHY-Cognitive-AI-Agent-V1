# TACHY Cognitive Brain OS - Deployment Runbook

This service must stay private until Phase 0 hardening is complete.

## Required Environment

Set these before production start:

```bash
APP_ENV=production
INTERNAL_API_KEY=<long-random-secret>
DB_URL=mysql+pymysql://tachy_brain:<password>@127.0.0.1:3306/tachy_brain
LLM_PROVIDER=anthropic
LLM_API_KEY=<provider-key-if-enabled>
TODY_EMAIL=<only-if-tody-connection-enabled>
TODY_PASSWORD=<only-if-tody-connection-enabled>
```

Production fails closed when `INTERNAL_API_KEY` is missing.

## Local Docker

```bash
cd /var/www/maa.tachy.in
cp .env.example .env
# edit INTERNAL_API_KEY, MYSQL_PASSWORD, MYSQL_ROOT_PASSWORD
docker compose up --build
```

Health check:

```bash
curl http://127.0.0.1:8200/health
curl -H "X-API-Key: $INTERNAL_API_KEY" http://127.0.0.1:8200/identity
```

## Database Migrations

Use Alembic for production schema changes:

```bash
alembic upgrade head
alembic revision --autogenerate -m "describe change"
```

`app/db/schema.sql` remains the bootstrap schema for fresh MySQL installs.
Alembic is the source of truth for incremental changes after deployment.

## Systemd Option

Example service:

```ini
[Unit]
Description=TACHY Cognitive Brain OS
After=network.target mysql.service

[Service]
WorkingDirectory=/var/www/maa.tachy.in
EnvironmentFile=/var/www/maa.tachy.in/.env
ExecStart=/var/www/maa.tachy.in/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8200
Restart=always
RestartSec=5
User=www-data
Group=www-data

[Install]
WantedBy=multi-user.target
```

## Nginx Reverse Proxy

Keep it behind HTTPS and pass the API key only from trusted clients.

```nginx
server {
    server_name maa.tachy.in;

    client_max_body_size 1m;

    location / {
        proxy_pass http://127.0.0.1:8200;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Before Public Exposure

1. Confirm `APP_ENV=production`.
2. Confirm `INTERNAL_API_KEY` is set and rotated outside git.
3. Run tests: `.venv/bin/pytest -q -p no:cacheprovider`.
4. Run migrations: `alembic upgrade head`.
5. Confirm `/health` works without key.
6. Confirm `/identity` fails without key and works with `X-API-Key`.
7. Confirm logs and DB backups are configured.
8. Keep write/action routes unavailable to browsers or public clients.

## Backup Basics

MySQL:

```bash
mysqldump -u tachy_brain -p tachy_brain > tachy_brain_$(date +%F).sql
```

SQLite development DB:

```bash
cp storage/tachy_brain.db storage/tachy_brain_$(date +%F).db
```
