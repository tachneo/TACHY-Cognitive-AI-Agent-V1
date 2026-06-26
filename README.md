# TACHY Cognitive Brain OS V1

> **AGI Phase-1** — a controlled cognitive foundation (the *brain base*), not a chatbot.
> Coding, security, ERP, TODY, business, and automation agents run **on top** of this layer.

- **Name:** TACHY Cognitive AI
- **Guardian / final authority:** Rohit Kumar (Founder of TODY, CTO/Head of Technology, TACHY EDTECH PRIVATE LIMITED)
- **Domain:** maa.tachy.in
- **Stack:** Python 3.12+, FastAPI, MySQL/PostgreSQL (SQLAlchemy), optional Redis (working memory) + vector search (semantic memory)
- **Status:** Phase 1A scaffold — bootable foundation. Most brain modules are real stubs to be filled in phase by phase.

---

## Core principle

Human intelligence is not just answering questions. It runs a loop:

```
NEED → INTEREST → ATTENTION → OBSERVATION → EMOTION TAGGING → MEMORY → MEANING → DECISION → ACTION → REVIEW → LEARNING → PERSONALITY CHANGE
```

This system models that loop with memory, emotion-aware priority, interest modeling,
decision memory, behavior learning, self-review, ethics, and human approval.

---

## Brain architecture

```
TACHY Cognitive Brain OS V1
├── 1. Identity Core          app/brain/identity_core.py
├── 2. Need & Goal System     app/brain/need_system.py
├── 3. Attention System       app/brain/attention_system.py  (+ interest_system.py)
├── 4. Memory System          app/memory/*  (15 memory types)
├── 5. Reasoning System       app/brain/cognitive_loop.py + decision_engine.py
├── 6. Action System          app/agents/*
├── 7. Emotion-Aware Priority app/brain/attention_system.py  (priority engine)
├── 8. Ethics Layer (Gita)    app/safety/policy.py
└── 9. Learning Loop          app/brain/learning_engine.py + self_review.py
```

### Memory types (`app/memory/`)
working, episodic, semantic, procedural, emotional, decision, failure, interest,
behavior, relationship, project, risk, goal, belief, opportunity.

---

## Priority formula (emotion-aware)

```
priority_score =
    security_risk    * 3
  + money_impact     * 2
  + client_impact    * 2
  + urgency
  + guardian_interest
  + emotional_weight
```

A TODY production login bug outranks writing a LinkedIn hashtag — by design.

---

## Safety & approval tiers (`app/safety/`)

| Tier | Examples | Behavior |
|------|----------|----------|
| **Low** | explain, draft, summarize, review code, create checklist/proposal | auto-execute |
| **Medium** | code changes, config/migration suggestions, security recommendations | warn first |
| **High** | prod deploy, DB modification, delete files, send email/message, access secrets, change payment/fees, disable security, run VPS shell | **explicit Rohit approval** |
| **Forbidden** | malware, credential theft, hacking 3rd-party systems, auth bypass, destructive/exfiltration, illegal cyber activity | never |

## Ethics layer (Bhagavad Gita-inspired)
Dharma (right duty) · Karma (consequences) · Satya (truth, no fake confidence) ·
Ahimsa (no harm to people/data/systems/business) · Sanyam (self-control before action) ·
Vivek (wise discrimination) · Seva (serve students, schools, clients, society).

---

## Folder structure

```
maa.tachy.in/
├── app/
│   ├── main.py              # FastAPI entrypoint
│   ├── config.py            # env-driven settings
│   ├── brain/               # identity, need, interest, attention, loop, decision, simulation, self-review, learning
│   ├── memory/              # 15 memory subsystems + base
│   ├── safety/              # risk classifier, approval gate, policy, secret detector, injection guard, audit
│   ├── tools/               # code reader/auditor, php security checker, mysql read-only, doc/business writer
│   ├── agents/              # main, coding, security, business, erp, tody
│   ├── api/                 # chat, memory, decision, approval, projects, reflection routes
│   └── db/                  # models.py, schema.sql, migrations/
├── tests/
├── storage/logs/
├── requirements.txt
├── .env.example
└── docker-compose.yml
```

---

## Run (local dev)

```bash
cd /var/www/maa.tachy.in
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit DB creds + LLM key
mysql -u USER -p < app/db/schema.sql   # create tables
uvicorn app.main:app --host 127.0.0.1 --port 8200 --reload
```

Health check: `GET http://127.0.0.1:8200/health`

> Serve publicly the same way as faceapi: nginx on `maa.tachy.in` → reverse-proxy to `127.0.0.1:8200`.
> **Not wired into nginx yet** — kept isolated from live projects until you approve.

---

## Build phases

| Phase | Goal |
|-------|------|
| **1A** | Cognitive Brain OS skeleton *(this scaffold)* |
| **1B** | Memory + priority + decision engines fully implemented |
| **1C** | Coding / security / business agents |
| **1D** | TODY app connection |
| **1E** | Controlled automation |
| **1F** | Continuous self-improvement |

First build the **brain base**, then attach skills.
