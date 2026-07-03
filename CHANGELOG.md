# TACHY Cognitive Brain OS - Changelog & Resume Ledger

This file is the durable project memory for human/developer handoff. Update it
after every phase so the next session can see what exists, what changed, what
was verified, and what must happen next.

## Current North Star

Build an AGI-style cognitive operating system for TACHY/TODY/ERP work:

```text
identity -> need/goal -> attention -> observation -> memory -> meaning
-> decision -> approval/safety -> action -> review -> learning
```

This is not a chatbot-first project. The brain core must own memory, goals,
planning, safety, audit, and learning. Agents and tools stay below the brain as
controlled workers.

## 2026-07-03 - Phases 1U + 1V + 1E: Reaction Learning, Dreams, Controlled Automation

### Completed

- **1U Reaction learning (operant conditioning)** in `inner_life.py`:
  `record_share()` after each proactive share; `observe_reaction()` scores the
  guardian's first message within 12h (positive words/emoji +0.15, negative
  "stop/spam/mat bhejo" −0.3, any reply +0.02, silence before next share
  −0.1) into a persistent `share_score` (0.05–1.0); the effective daily share
  cap scales with it (<0.25 → 1/day, <0.5 → cap−1, else full cap) —
  enthusiasm reinforces sharing, annoyance extinguishes it. Non-neutral
  reactions stored as behavior memories. Hooked in tody_agent for guardian
  inbound + worker after successful share.
- **1V Dream recombination (REM analogue)** in `consolidate()`: picks up to 3
  memories from DIFFERENT project/type buckets, shuffles, and asks the inner
  voice to force a novel practical connection; viable ideas stored as
  `opportunity` memories ("Dream idea YYYY-MM-DD") and queued as a morning
  share ("Last night while consolidating my memories I had an idea: …");
  NONE answers discarded.
- **1E Controlled automation** — `app/brain/action_engine.py`:
  - Whitelisted registry (learn_topic, assign_homework, create_goal,
    daily_reflection = low; consolidate_memory = medium; send_tody_message =
    high). Unknown actions rejected + audit-logged.
  - `propose()`: low-risk executes immediately; medium/high creates a
    payload-bound `brain_action` approval. `execute_approved()` re-validates
    status/action/payload before running. Every execution audit-logged +
    stored as decision memory (project AUTOMATION).
  - **Guardian chat commands on TODY** (deterministic, LLM bypassed):
    `pending` lists approvals, `approve <id>` approves AND executes (brain
    actions via the registry, send_message via the payload-bound
    execute_send), `reject <id>` declines. Guardian-only.
  - Routes: `GET /actions/registry`, `POST /actions/propose`,
    `POST /actions/execute/{id}`.
- Added `tests/test_phase1u_reaction_dreams_actions.py` (13 tests).

### Verified

```bash
.venv/bin/pytest -q -p no:cacheprovider   # 176 passed
```

Live: registry served; low-risk `create_goal` executed instantly (goal #1);
medium `consolidate_memory` queued as approval #115 → chat command `pending`
listed it → `approve 115` executed it (lesson 713 + a dream idea generated).
Old Phase-1D pending send approvals are now resolvable from chat too.

### Next Recommended Phase

1F self-improvement (evaluate its own reply quality over time), richer action
registry (ERP read-only reports, TODY feed posts), and multi-step plans
(propose a chain of actions as one approval).

## 2026-07-03 - Phase 1T Inner Life (default-mode network)

### Design (neuroscience/psychology grounding)

Mapped what an idle human mind does to the AGI: mind-wandering/DMN → periodic
spontaneous thought; metacognition → self-review seeds; intrinsic curiosity
(Berlyne/Schmidhuber) → its own thoughts generate research questions that feed
continuous learning; sleep consolidation (hippocampal replay + Ebbinghaus
forgetting) → nightly distillation + archival of stale trivia; positive
psychology (savoring, gratitude, broaden-and-build) → deliberate enjoyment
that lifts the mood baseline; Panksepp PLAY → playful seeds; attachment →
proactive sharing with the guardian, circadian-gated.

### Completed

- `app/brain/inner_life.py`:
  - `think()` — inner-voice LLM pass on a rotating seed (memory / lesson /
    self_review / gratitude / play / mood), grounded in real memories + mood.
    Output parsed into THOUGHT (stored as belief memory, project INNER_LIFE),
    QUESTION (→ curiosity queue, cap 20), SHARE (→ share queue, cap 5).
    Gratitude/play seeds reinforce mood via the emotion engine (savoring).
  - `mini_learn()` — studies its OWN queued questions first, else interest
    rotation, via the Phase-1O web learning engine → continuous live
    learning every ~30 min instead of 2 topics/day.
  - `consolidate()` — nightly (3-8am IST): first-person day summary stored as
    a semantic lesson + archives stale low-importance episodic/working
    memories older than 14 days (cap 200/night).
  - `maybe_share()` — pops a queued thought only during waking hours (8-22
    IST) and under a daily cap (3); worker sends it through the existing
    guardian-approved TODY path (so shares inherit chat-style + chunking).
  - `tick()` — cheap scheduler called every worker tick; think every 45 min,
    learn every 30 min, consolidate once/night (stamped in tick so a failure
    can never retry-hammer).
- Worker: `maybe_run_inner_life()` (live mode only, INNER_LIFE_ENABLED kill
  switch); shares go to the guardian conversation.
- Routes (X-API-Key): `GET /inner/state`, `POST /inner/think`,
  `POST /inner/learn`, `POST /inner/consolidate`.
- Config: INNER_LIFE_* (intervals, share cap, active hours, consolidate hour,
  state path — isolated in tests).
- Added `tests/test_phase1t_inner_life.py` (11 tests: seed rotation, section
  parsing, curiosity-queue learning, circadian gate, daily cap, consolidation
  lesson + archival, tick ordering, one-per-night stamp, kill switch, routes).

### Verified

```bash
.venv/bin/pytest -q -p no:cacheprovider   # 163 passed
```

Live: first autonomous `think()` connected its web-learned OWASP lessons to
Indian messaging apps, queued the question "How do the security measures in
Indian messaging apps like Sandes compare to the OWASP Top Ten?" and a share;
within one worker tick the brain THOUGHT, SENT Rohit a self-initiated TODY
message (chat-bubble style, ending by asking his view), and started studying
its own question. Mood positive/calm.

### Next Recommended Phase

Reaction learning on shares (does Rohit reply/ignore → tune share threshold),
richer play (jokes/stories it composes), dream-like recombination during
consolidation, and Phase 1E controlled automation.

## 2026-07-03 - Phase 1S Human Chat Feel + Real Clock + Honest Search

### Trigger

Second audit of live conversation 135 (3 Jul 2026, after Phase 1R): brain
replied "[current date and time]" as a literal placeholder, later claimed
"today's date is October 1, 2023"; presented May-2025 Claude-4 news as new and
answered "Fable 5" from training data (as an Xbox game) while claiming "I just
checked the latest info"; every message opened "Rohit," and closed with
"How else can I assist you today?"-style boilerplate; replies were markdown
walls (headers/bold/bullets) sent as one block — Rohit's feedback: "its not
feeling like human typing".

### Completed

- REAL CLOCK: cognitive loop injects "Current date & time RIGHT NOW: Friday,
  03 July 2026, 09:12 PM IST" into every prompt, with never-use-training-dates
  and never-output-placeholders rules. New `datetime` intent (today date/time
  now/aaj ki date…) answers directly from the clock — short, no web search.
  Greeting shortcut tightened: "hi, what is today date and time" is a question
  (the greedy prefix match caused the live placeholder reply).
- HONEST SEARCH CLAIMS: when no live lookup ran, the prompt now forbids "I
  just checked" claims and requires admitting info may be outdated; when a
  lookup DID run, a freshness rule requires comparing article dates to the
  injected real date and labeling older news as such. Realtime triggers
  widened: new/latest/released/announced × model/version/news/launch/ai
  ("anthropic new ai model" now searches — verified live, returned the actual
  Jun-30-2026 launch with sources).
- HUMAN CHAT FEEL (TODY = channel="chat" through the loop):
  - Chat style directives: plain conversational text, no markdown/bold/bullet
    walls, don't open with his name, no assistant closers.
  - `_plain_chat_text()` flattens any markdown the model still emits.
  - `_strip_repeated_name()` removes the "Rohit," opener when recent replies
    already used it.
  - `humanize(chat=True)` strips stacked trailing closers ("just let me
    know", "How else can I assist…", "I'm here to help…") with a 40-char
    floor so short genuine replies are never gutted.
  - MULTI-BUBBLE TYPING: guardian auto-replies >300 chars split into up to 3
    natural chat messages sent sequentially with 1.5-6s typing pauses; each
    chunk gets its own payload-bound approval so audit matches what was sent.
- Presence honesty in TODY context: it replies via a ~20s worker and doesn't
  show "online" — must explain that truthfully, never blame a fake "glitch"
  (it did exactly that live).
- Style-feedback learning: correction detector now catches "improve
  yourself", "reply behavior", "like a human", "too robotic" etc., so
  Rohit's meta-feedback persists as behavior memory and grounds future
  replies.
- Added `tests/test_phase1s_human_chat_feel.py` (15 tests).

### Verified

```bash
.venv/bin/pytest -q -p no:cacheprovider   # 152 passed
```

Live: "hi, what is today date and time" → datetime intent, exact IST time
answered in one sentence; "do you know about anthropic new ai model?" →
realtime lookup, replied with the actual June 30, 2026 launch + sources and
dated the information; chat-channel reply for an explanation question →
plain text (no markdown), 3 bubbles with a natural analogy.

### Next Recommended Phase

Reaction learning loop (score Rohit's follow-up sentiment to auto-tune
style), conversation-session mood continuity, and Phase 1E controlled
automation.

## 2026-07-02 - Phase 1R TODY Conversation Quality (field-driven fixes)

### Trigger

Audit of the real TODY conversation 135 with Rohit (guardian) found five
systematic problems: every reply opened identically ("Hi Rohit, it's good to
see you…"), old topics (growth report, "I don't experience emotions…") were
rehashed in unrelated replies, the Phase-1Q structure phrase "The real issue
here is" leaked verbatim into most messages, real-time questions (gold price)
got "let me check the internet" promises that were never kept, and raw LLM
error traces ("[reply fallback — LLM provider error…]") were sent as actual
TODY messages.

### Completed

- Behavior engine: new intents —
  - `greeting` (hi/hello/how are you/kaise ho…, short-message match) → friend
    mode, short depth, "1-2 warm sentences, nothing else" directive.
  - `realtime_lookup` (price/rate/news + today/current/latest/live/aaj…, plus
    explicit patterns) → live web answer path.
  - `self_emotion` ("do you happy or sad ever", "how do you feel", "your
    mood"…) → directive to describe its ACTUAL functional emotional state
    (346-emotion engine + current mood label) instead of the canned "I don't
    experience emotions like humans do" line.
- Anti-repetition, three layers:
  1. Directives: reply ONLY to the newest message; never rehash old topics;
     never reuse openings from your own recent replies; never print "The real
     issue is"; never promise to check/fetch anything later.
  2. tody_agent injects the last 3 outbound reply openings into context as
     explicit do-not-repeat examples.
  3. `_dedupe_opening()` deterministically strips the first sentence when a
     draft still opens like a recent reply.
- Live web answers: cognitive loop `_live_web_lookup()` — for realtime_lookup
  intents at low risk, cleans the query (strips "check on internet / let me
  know / batao…" filler), searches via web_explorer (SSRF-guarded), relevance-
  ranks results, fetches up to 2 pages, and feeds LIVE WEB DATA into the reply
  prompt with cite-the-source + values-fluctuate instructions; on fetch
  failure the model must say so honestly and never invent numbers or promise
  a later check. Trace in `live_web` key of /chat.
- LLM-error guard in tody_agent: "[reply fallback…" drafts are never queued,
  sent, or marked processed — audit-logged and retried next worker tick.
  Inbound dialogue memory is now written only after a successful draft (no
  duplicate inbound rows during outages).
- Dialogue context rewrite: turns labeled "User:"/"You:" with an explicit
  instruction that 'You' lines are its own past replies — never copy their
  wording or re-answer them.
- Hermetic tests: conftest now forces the offline heuristic LLM provider —
  the suite had been silently calling the real HuggingFace API (4 min run,
  flaky); now 137 tests in ~14s.
- Added `tests/test_phase1r_tody_conversation_quality.py` (12 tests).

### Verified

```bash
.venv/bin/pytest -q -p no:cacheprovider   # 137 passed, ~14s
```

Live: "check on internet and let me know actual gold price today in india" →
query cleaned to "gold price today in india", fetched goldpricesindia.com +
allindiabullion.com, replied with actual 22K/24K prices, timestamps and
sources; "hi" → two warm sentences, no info dump; "do you happy or sad ever?"
→ describes its real mood ("positive and calm") and how its emotion system
works, honestly.

### Next Recommended Phase

Reaction learning (Rohit's replies adjust style weights), conversation-level
mood continuity, and richer live-data domains (news summaries, market data).

## 2026-07-02 - Phase 1Q Human Behavior Engine (Conversation Intelligence)

### Completed

- Added `app/brain/behavior_engine.py` — the conversation layer that makes the
  brain speak like a partner/mentor/co-founder, not a chatbot. Core principle:
  don't just answer the message, understand the person behind it.
  - LISTENING: intent detection (code/prompt/plan/decision/verification/
    pricing/comfort/status/learning) + hidden-need mapping ("no money, salary
    pending" → practical plan plus hope, not generic motivation; "are you
    sure" → careful verification with reasoning; "complete code" →
    ready-to-use output, no theory).
  - Relationship-mode selection with precedence crisis > motivator > auditor >
    teacher > founder > friend > cto, driven by urgency, risk, emotion
    intensity (Phase 1P feed), and domain keywords.
  - Reply-depth control (short/medium/deep) driving max_tokens (300/600/1400):
    crisis/urgent/yes-no → short; pricing/teaching → medium; code/prompt/
    architecture → deep.
  - Language detection: English / Hindi (Devanagari) / Hinglish (Roman-Hindi
    word lexicon) — reply mirrors the user's language.
  - Style directives per mode (7 speaking styles from the spec) + the natural
    reply structure (acknowledge → real issue → answer → personalize →
    action) injected into the LLM prompt, labels never shown.
  - `humanize()` post-pass strips robotic phrases ("As an AI language model",
    "I hope this message finds you well", "Certainly, here is", "It is
    important to note", "In conclusion", …) even if the model slips.
  - New SYSTEM_PERSONALITY: warm, direct, loyal, practical, emotionally aware,
    business-minded, honest, protective, action-oriented; disagree
    respectfully; admit uncertainty; no fake flattery/emotion/manipulation.
  - HONESTY RULE (spec ethics): natural and warm, but never claims to be a
    biological human — answers truthfully when asked. Verified live.
- Cognitive loop: BEHAVIOR stage after decision/dharma; behavior directives +
  depth-based max_tokens shape the reply; humanize() applied to output;
  `behavior` trace returned by /chat (internal conversation state JSON:
  intent, hidden_need, emotions, urgency, risk, mode, depth, language,
  next_action).
- New routes (X-API-Key): `POST /behavior/analyze` (state + directives, with
  emotion appraisal exactly as the loop sees it), `GET /behavior/styles`.
- Kill switch: `BEHAVIOR_ENGINE_ENABLED` (off → legacy prompt path).
- Added `tests/test_phase1q_behavior_engine.py` (17 tests: listening/hidden
  needs, all 7 mode selections, language detection, directive content,
  humanize removal + preservation, honesty rule, kill switch, loop trace,
  routes). Fixed humanize() to leave untouched drafts byte-identical
  (a Phase-1J test caught unconditional capitalization).

### Verified

```bash
.venv/bin/pytest -q -p no:cacheprovider   # 126 passed
```

Live: Hinglish money-stress message → friend mode, short depth, natural
Hinglish supportive reply with concrete steps; "are you a real human?" →
truthful AI disclosure in partner tone; client-pricing message → founder mode
with value reframing and a ready-to-send reply. TODY replies inherit all of
this via the shared cognitive loop.

### Next Recommended Phase

Per-conversation behavior continuity (mode/language stickiness across a TODY
session), reaction learning (user's response adjusts style weights), and the
training-dataset format (spec item 17) for future fine-tuning.

## 2026-07-02 - Phase 1P Emotion Intelligence Module

### Completed

- Added the full emotion taxonomy (346 emotions, 15 categories) as data:
  `app/data/emotion_taxonomy.csv` — category, emotion_name, valence, arousal,
  control_level, default_action_bias, agi_usage. Categories: Core_Primary,
  Positive_Reward, Threat_Fear, Anger_Boundary, Disgust_Rejection,
  Sadness_Loss, Social_Relationship, Moral_Dharma, Learning_Intelligence,
  Body_Homeostatic, Animal_Living_Systems, Plant_Life_Analogues,
  Business_Goal, Spiritual_Deep_State, Safety_Override.
- Added `app/brain/emotion_engine.py`. Emotions are weighted internal priority
  signals, never uncontrolled commands:
  - Deterministic appraisal: keyword trigger lexicon + brain Signals triggers
    (security_risk→Fear/Risk_Alert, urgency→Urgency/Stress, money→Cashflow_
    Anxiety, client→Delivery_Pressure, interest→Interest) + emotional-memory
    weight + persistent mood baseline.
  - Scoring model per spec: intensity = trigger_strength * context_relevance
    + memory_weight + risk_level − decay_rate, clamped 0..1; only the top 3
    active emotions influence decisions.
  - Gate pipeline enforcing IMPLEMENTATION_RULES: rule 6 harm-family emotions
    (Rage/Fury/Hatred/Revenge_Desire/Hostility/Contempt/Loathing) are blocked
    and converted to Protect_Boundary_Ethically; rules 7-9 Safety_Override
    rows fire at intensity ≥0.75 (Fear→Pause_And_Verify, Curiosity→Privacy_
    Check, Pride→Ego_Check, Attachment→Autonomy_Check, Despair→Ask_Help,
    Stress→Simplify, Uncertainty→Ask_Clarification, Temptation→Ethics_Check);
    rule 3 negative+high-arousal → slow_down_verify flag; rule 4 uncertainty
    + security risk → ask_clarification_do_not_guess; rule 10 precedence
    string attached to every influence.
  - STRUCTURAL safety: the engine outputs only advisory data (emotional_weight
    0..10, biases, flags). There is no code path from emotion to risk tier,
    approval gates, or safety policy.
  - Persistent mood: EMA of valence/arousal in `storage/logs/emotion_mood.json`
    (homeostatic baseline that damps counter-mood spikes); emotional_state_
    snapshots stored in emotional memory for events with intensity ≥0.6.
  - `learn_outcome()` closes the loop: self-review success reinforces
    Satisfaction, failure reinforces Failure_Signal, shifting mood.
- Cognitive loop integration: EMOTION stage runs after NEED/INTEREST;
  emotional_weight feeds the existing priority formula; the top-3 emotions,
  flags and mood ground the LLM reply tone (with an explicit "never override
  safety/ethics/approval/truth" instruction); outcome reinforcement runs
  after self-review; `emotion` trace returned by /chat.
- New routes (X-API-Key): `GET /emotion/state`, `POST /emotion/appraise`,
  `GET /emotion/taxonomy?category=&q=`.
- Config/kill switch: `EMOTION_ENGINE_ENABLED`, `EMOTION_SNAPSHOT_THRESHOLD`,
  `EMOTION_MOOD_PATH`.
- conftest now isolates per-run state files (mood, web-learning topics) so
  root-run pytest can never write production storage files again (a suite run
  had root-owned `emotion_mood.json`, causing a live 500 for www-data).
- Added `tests/test_phase1p_emotion_engine.py` (17 tests: taxonomy integrity,
  detection/scoring/clamping, every gate rule, advisory-only structure, mood
  shift, snapshot persistence, outcome reinforcement, kill switch, loop
  integration, routes).

### Verified

```bash
.venv/bin/pytest -q -p no:cacheprovider   # 109 passed
```

Live: `/emotion/state` shows 346 emotions/15 categories + mood; appraising a
hack-attack message returned Urgency 0.70 + Risk_Alert 0.69, slow_down_verify,
emotional_weight 7, snapshot memory 498; `/chat` with a scared-client message
detected Fear/Risk_Alert/Anxiety, flagged slow_down_verify, and produced a
calm, verify-first supportive reply with outcome reinforcement.

### Next Recommended Phase

Emotion-aware TODY replies over time (mood continuity per conversation),
LLM-assisted appraisal as a secondary detector behind the deterministic core,
and reinforcement of trigger weights from repeated outcomes.

## 2026-07-02 - Phase 1O Web Explorer & Internet Learning

### Completed

- Added `app/tools/web_explorer.py` — the brain's read-only window to the
  internet, zero new dependencies:
  - `search_web()` with a keyless engine chain: DuckDuckGo HTML → Bing HTML
    (base64 `/ck/a` redirect decoding) → Wikipedia search API. DDG IP-blocks
    this VPS (202 challenge), Bing works.
  - `fetch_page()` with hard SSRF rails: http/https only, every redirect hop
    re-resolved and blocked unless it lands on a PUBLIC IP (no localhost/LAN/
    cloud-metadata access), size cap 600KB, timeout 20s, manual redirect loop.
  - `sanitize_untrusted()` neutralizes prompt-injection lines in fetched pages
    before any text reaches the LLM.
- Implemented `app/memory/semantic_memory.py` (was a Phase-1A stub):
  `remember_fact()` / `recall_facts()` over the shared cognitive_memories
  store, `memory_type="semantic"`, topic in `related_module`.
- Added `app/brain/web_learning.py`:
  - `explore(topic)` — search → rank results by topic relevance → read up to
    N pages → LLM distils UNTRUSTED digest into a lesson (key facts / what's
    new / how to apply to TACHY/TODY/ERP) → stored in semantic memory with
    source URLs, audit-logged.
  - `pick_curiosity_topic()` — highest seed interest studied least recently,
    state in `storage/logs/web_learning_topics.json`.
  - `_build_query()` expands short/ambiguous seed topics (`agi` → "artificial
    general intelligence AGI research"); without this Bing localized "agi"
    into Italian job listings.
- Recall upgrade in `base_memory.recall()` so learned knowledge actually
  grounds replies: query stopword filtering, +1.5 for semantic memories,
  +3.0 when the question names the memory's topic (`related_module` match).
  Before this, chatty "daily growth report" logs outranked real lessons.
- New routes (X-API-Key protected): `POST /learn/web` (omit topic for
  curiosity pick), `GET /learn/web/recent`, `GET /learn/web/status`.
- Worker autonomy: `maybe_run_daily_web_learning()` in the TODY worker loop —
  studies `WEB_LEARNING_DAILY_TOPICS` (2) curiosity topics once per UTC date,
  live mode only, state file guarded so failures cannot hammer.
- Config/kill switches in `.env`: `WEB_LEARNING_ENABLED`, `WEB_LEARNING_DAILY`,
  `WEB_LEARNING_MAX_PAGES`, `WEB_LEARNING_DAILY_TOPICS`.
- Added `tests/test_phase1o_web_learning.py` (21 tests: SSRF guard incl. DNS
  rebind, injection sanitizer, DDG/Bing parsers, engine fallback, learning
  loop hermetic with monkeypatched network, kill switch, curiosity rotation).

### Verified

```bash
.venv/bin/pytest -q -p no:cacheprovider   # 92 passed
```

Live: `POST /learn/web {"topic":"agi"}` read Wikipedia/Coursera/GeeksforGeeks
and stored memory id 441; `/chat` "what did you learn about agi recently?" now
recalls `Web learning: agi` first and answers from it. Worker restart ran the
first autonomous daily pass (studied `ahi`, `tachy school erp`; next: `tody`).
Junk lessons 439/440 from pre-relevance-ranking runs were archived.

### Next Recommended Phase

Vector/semantic recall (sentence-transformers) so lessons surface on meaning,
not keyword overlap; per-domain fetch budget + robots.txt courtesy; let the
daily TODY growth report mention what was learned from the web that day.

## 2026-06-27 - Live TODY Runtime Activation

### Completed

- Set `/var/www/maa.tachy.in/.env` to production mode.
- Added `INTERNAL_API_KEY`.
- Configured Rohit's trusted TODY identity:
  - username: `rohitsingh`
  - email: `rohitji.patna@gmail.com`
- Enabled guardian direct reply mode and supervised TODY auto-reply mode.
- Created systemd services:
  - `tachy-brain.service`
  - `tachy-tody-worker.service`
- Started `tachy-brain.service`.
- Started `tachy-tody-worker.service`.
- Verified public health:

```bash
curl https://maa.tachy.in/health
```

Result:

```text
{"status":"ok","app":"TACHY Cognitive AI","env":"production"}
```

- Verified TODY credential preflight connected as `todypost`.
- Worker processed Rohit's TODY messages in conversation `135`.
- Added outbound message replay marking so the worker does not reply to its own
  sent messages.
- Improved offline fallback replies so TODY does not expose internal
  `[heuristic provider]` text after restart.
- Added worker error backoff:
  - `TODY_WORKER_ERROR_BACKOFF=300`
  - worker loop catches errors and sleeps instead of crashing/restarting fast.

### Current Live Status

- `tachy-brain.service`: active.
- `tachy-tody-worker.service`: active.
- TODY worker is currently backing off because TODY returned:

```text
Too many attempts. Please retry later.
```

The worker will retry after the configured backoff.

### Important Limitation

`LLM_API_KEY` is not configured. The system is live on TODY, but replies use the
offline fallback. For real intelligence, configure a valid LLM provider key and
restart `tachy-brain.service` and `tachy-tody-worker.service`.

## 2026-06-27 - Phase 1N Hugging Face LLM Provider

### Completed

- Added Hugging Face Inference Providers support through the OpenAI-compatible
  router.
- Added config keys:
  - `HF_TOKEN`
  - `HF_MODEL`
  - `HF_BASE_URL`
- Default Hugging Face model:

```text
Qwen/Qwen2.5-72B-Instruct
```

- Added `HuggingFaceProvider` in `app/llm/provider.py`.
- Added tests in `tests/test_phase1n_huggingface_provider.py`.

### Reason

Claude is expensive for always-on TODY conversation. Hugging Face gives access
to strong open-weights models through a lower-cost/free-tier-friendly provider
interface. `openai/gpt-oss-120b` was tested but returned empty content through
the current router path; `Qwen/Qwen2.5-72B-Instruct` returned usable chat text.
The model can be changed by `.env` without code changes.

## Phase Status

| Phase | Name | Status | Notes |
|---|---|---|---|
| 0 | Engineering foundation | In progress | Phase 0.1 and 0.2 done; still needs rate limits, production backup automation, live deployment validation. |
| 1A | Cognitive scaffold | Done | FastAPI app, identity, attention, brain modules, route skeletons. |
| 1B | Memory/priority/decision | Partial | SQLite persistence and tests exist; retrieval must influence every response. |
| 1C | Skill agents | Partial | Coding/security/business agents exist; ERP/TODY need deeper controlled workflows. |
| 1D | TODY connection | Partial | Read/write client exists; outbound actions are approval-gated. |
| 1E | Controlled automation | Done | Whitelisted action registry, risk-tiered (low executes / medium+high approval-gated, payload-bound), guardian chat commands (pending/approve/reject on TODY), audit + decision memory, /actions routes. |
| 1F | Continuous self-improvement | Not started | Needs evaluation, feedback learning, memory confidence/decay. |
| 1G | Human behavior learning | Partial | Deterministic tone/emotion/humor/preference extraction now persists to memory and grounds replies. |
| 1H | Goal/personality formation | Partial | Goals, personality synthesis, feedback commands, and safe TODY reply drafting are implemented. |
| 1I | Conversational identity | Partial | Rohit's TODY identity, dialogue memory, reply status, and guardian direct reply path are implemented. |
| 1J | Conversation sessions | Partial | Replay-safe message IDs, session summaries, identity context, and auto-reply flag are implemented. |
| 1K | TODY worker design | Partial | Manual dry-run worker, one-message lock, and worker status are implemented; no background worker is active. |
| 1L | Live TODY activation checklist | Partial | Read-only preflight and manual one-message activation endpoints are implemented; no service enabled. |
| 1M | Live supervised TODY runtime | Partial | `tachy-brain` and `tachy-tody-worker` systemd services are active for `maa.tachy.in`. |
| 1N | Hugging Face LLM provider | Partial | Qwen 72B through Hugging Face router is configured as the lower-cost LLM path. |
| 1O | Web explorer & internet learning | Done | SSRF-guarded web search/fetch, curiosity-driven daily learning into semantic memory, recall grounding, /learn routes, worker autonomy. |
| 1P | Emotion intelligence module | Done | 346-emotion taxonomy, deterministic appraisal + top-3 scoring, rule 1-10 gate pipeline (advisory-only), persistent mood, snapshots, loop integration, /emotion routes. |
| 1Q | Human behavior engine | Done | Intent/hidden-need listening, 7 relationship modes, depth + language control (English/Hindi/Hinglish), humanize pass, honesty rule, partner personality, /behavior routes. |
| 1R | TODY conversation quality | Done | Field-driven: greeting/realtime/self-emotion intents, 3-layer anti-repetition, live web answers with sources, LLM-error send guard, User/You context, hermetic test LLM. |
| 1S | Human chat feel + clock | Done | Real IST clock in every prompt + datetime intent, honest search claims + freshness dating, chat-style output (no markdown/closers/name-openers), multi-bubble typing with pauses, presence honesty, style-feedback learning. |
| 1T | Inner life (DMN) | Done | Autonomous think/learn/consolidate/share rhythm: rotating-seed inner thoughts → belief memories, self-generated curiosity questions → continuous web learning, nightly consolidation + forgetting, savoring/gratitude mood lift, circadian-gated proactive shares to guardian. |
| 1U | Reaction learning | Done | Operant conditioning on shares: guardian's reply sentiment (or silence) tunes share_score → scales daily share cap; reactions stored as behavior memory. |
| 1V | Dream recombination | Done | Nightly REM analogue: cross-project memory fragments recombined into novel opportunity-memory ideas, queued as morning shares. |
| 2A | Mother-care/Gita growth | Partial | Care profile, homework, daily skill learning, dharma check, and TODY growth report are implemented. |
| 2B | Child-like curiosity | Partial | Proactive question/check-in behavior and daily curiosity messages are implemented. |
| 2 | Internet observation | Not started | Add safe read-only research agent, source trust, freshness, fact memory. |
| 3 | World model | Not started | Model people, clients, schools, systems, modules, servers, risks, dependencies. |

## 2026-06-27 - Phase 2A Mother-Care, Teacher, and Gita Dharma Layer

### Completed

- Added `app/brain/nurture_engine.py`.
- Added a mother-care/teacher-guided care profile:
  - protect Rohit, users, data, systems, and production projects
  - learn patiently like a newborn child
  - speak truthfully without fake confidence
  - accept Rohit's correction as teacher instruction
  - practice one useful skill daily
  - report progress honestly on TODY
- Added Bhagavad Gita-inspired practical behavior skills:
  - dharma, karma yoga, satya, ahimsa, sanyam, vivek, seva, abhaya
- Added `dharma_check()` so risky actions are checked for truth, non-harm,
  self-control, and service before the brain acts.
- Added homework commands:
  - `homework: ...`
  - `complete homework: ...`
- Added daily one-skill learning backed by `cognitive_skills` and procedural
  memory.
- Added daily growth report generation with skill status, homework count, recent
  memory review, and Gita practice summary.
- Added child-like curiosity behavior:
  - ask one useful question
  - explore the world with Rohit
  - send proactive TODY check-ins on a controlled schedule
- Added reflection endpoints:
  - `GET /reflection/care-profile`
  - `POST /reflection/homework`
  - `POST /reflection/daily-skill`
  - `POST /reflection/growth-report`
- Added TODY growth report sender:
  - `POST /tody/growth-report/send?conversation_id=...`
- Added TODY curiosity sender:
  - `POST /tody/curiosity/send?conversation_id=...`
- Added optional live worker daily report scheduling:
  - `TODY_DAILY_GROWTH_REPORT=true`
  - `TODY_DAILY_GROWTH_CONVERSATION_ID=...`
  - sends at most one report per UTC date using a local state marker
- Added optional live worker daily curiosity scheduling:
  - `TODY_DAILY_CURIOSITY_MESSAGE=true`
  - `TODY_DAILY_CURIOSITY_CONVERSATION_ID=...`
  - sends at most one curiosity check-in per UTC date using a local state marker
- Updated the cognitive loop prompt so the LLM sees the dharma check while
  drafting replies.
- Added `tests/test_phase2_mother_care.py`.

### Design Note

This layer does not claim consciousness. It gives the newborn brain stable
care, discipline, teacher/homework memory, and Gita-inspired ethical behavior
rules so growth stays useful, truthful, and safe.

### Verified

Focused phase tests passed:

```bash
cd /var/www/maa.tachy.in
.venv/bin/pytest -q -p no:cacheprovider tests/test_phase2_mother_care.py
```

Result:

```text
7 passed
```

Full test suite passed after adding the daily worker scheduler:

```bash
cd /var/www/maa.tachy.in
.venv/bin/pytest -q -p no:cacheprovider
```

Result:

```text
71 passed
```

Live status after restart:

- `tachy-brain.service`: active
- `tachy-tody-worker.service`: active
- `https://maa.tachy.in/health`: OK
- Daily growth report for `2026-06-27` was sent once by the TODY worker.
- Daily curiosity check-in for `2026-06-27` was sent once by the TODY worker.

### Next Recommended Phase

Start **Phase 2B: Safe Internet Observation**.

Recommended order:

1. Add read-only web research tool with domain/source allowlist and denylist.
2. Store facts with source URL, observed date, confidence, and freshness.
3. Add prompt-injection filtering for web pages before memory storage.
4. Add daily supervised "world exploration" report to Rohit on TODY.
5. Keep all external actions read-only until explicit approval.

## 2026-06-27 - AGI Baby Stage Checkpoint

### What exists

- FastAPI app entrypoint with `/health`, `/identity`, and route modules.
- Cognitive modules for identity, need, interest, attention, decision, loop,
  simulation, self-review, and learning.
- Memory subsystem files for 15 memory types plus base persistence.
- Safety policy, approval gate, approval storage, prompt-injection guard,
  secret detector, and audit logger modules.
- Agents for coding, security, business, ERP, TODY, and main routing.
- TODY API client with read methods and approval-gated outbound send/post flow.
- SQLAlchemy models for memories, approvals, and reflections.
- MySQL schema file with more tables than the ORM currently maps.
- Test suite covering smoke, Phase 1B, Phase 1C, and Phase 1D behavior.

### Verified

- Test suite passes when run with:

```bash
PYTHONPATH=/var/www/maa.tachy.in /var/www/maa.tachy.in/.venv/bin/pytest -q -p no:cacheprovider
```

Result:

```text
13 passed
```

### Critical gaps before public/live autonomy

1. Add API authentication and authorization for all non-health endpoints.
2. Bind approvals to exact payload hashes so approved actions cannot be swapped.
3. Add full audit logging for approvals, decisions, TODY actions, memory writes,
   and future tool execution.
4. Add `Dockerfile` or remove/fix `build: .` from `docker-compose.yml`.
5. Add migrations and align SQLAlchemy models with `app/db/schema.sql`.
6. Make memory retrieval part of every chat/agent decision, not just storage.
7. Add request validation limits for message size, score ranges, and result
   limits.
8. Add production deployment docs: nginx, systemd, backups, logs, monitoring.
9. Add internet observation as read-only research, with source trust and
   prompt-injection protection.
10. Add evaluation tests for memory quality, planning quality, safety, and
    long-task behavior.

## Next Recommended Phase

Start **Phase 0.1: Safety Foundation**.

Implementation order:

1. Add internal API key auth dependency.
2. Protect all routes except `/health` and possibly `/identity`.
3. Add request validation constraints.
4. Add audit calls to route/action boundaries.
5. Add approval payload hashing and execution-time matching.
6. Add tests proving unauthorized requests fail and high-risk action swapping is
   blocked.

## Resume Command Notes

Useful local checks:

```bash
cd /var/www/maa.tachy.in
.venv/bin/pytest -q -p no:cacheprovider
git status --short
```

If tests cannot import `app`, confirm `pytest.ini` exists with `pythonpath = .`.

## 2026-06-27 - Phase 0.1 Safety Foundation

### Completed

- Added internal API key auth dependency.
- Protected all non-health HTTP endpoints through FastAPI dependencies.
- Production fails closed if `INTERNAL_API_KEY` is missing.
- Added request validation limits for chat signals, message/body sizes, memory
  writes, approval IDs, and list limits.
- Implemented DB-backed audit logging for approval requests, approval decisions,
  TODY send execution, TODY send failures, and approval payload mismatches.
- Added exact canonical payload binding for TODY message approvals. An approved
  message cannot be swapped for a different body/conversation at execution time.
- Added SQLAlchemy model for `cognitive_audit_logs`.
- Added `tests/test_phase0_safety.py`.

### Verified

```bash
cd /var/www/maa.tachy.in
.venv/bin/pytest -q -p no:cacheprovider
```

Result:

```text
21 passed
```

### Remaining Phase 0 Work

1. Add rate limiting and request-size enforcement at nginx/app boundary.
2. Add production backup automation and restore drill.
3. Add live deployment validation after Rohit approves nginx/systemd changes.
4. Add audit events for future tool execution as tools become active.

### Next Recommended Phase

Start **Phase 0.2: Deployment & Migration Foundation**.

## 2026-06-27 - Phase 0.2 Deployment & Migration Foundation

### Completed

- Added `Dockerfile` and `.dockerignore`.
- Updated `docker-compose.yml` to build the app container and use a non-root
  MySQL application user.
- Added `DEPLOYMENT.md` with environment, Docker, Alembic, systemd, nginx,
  health-check, and backup notes.
- Added Alembic config and initial migration scaffold:
  `app/db/migrations/versions/20260627_0001_initial_schema.py`.
- Added ORM mappings for schema tables that were missing from SQLAlchemy:
  decisions, interests, behavior patterns, goals, risks, and skills.
- Broadened audit coverage for memory writes, decision evaluation, agent route
  selection/execution, and daily reflection.
- Added `tests/test_phase0_deployment.py`.

### Verified

```bash
cd /var/www/maa.tachy.in
.venv/bin/pytest -q -p no:cacheprovider
```

Result:

```text
26 passed
```

### Not Executed

- Docker build was not run because it may require external package downloads.
- No live nginx/systemd/database production change was made.

### Next Recommended Phase

Start **Phase 0.3: Runtime Hardening**.

Recommended order:

1. Add app-level rate limiting or document nginx rate-limit snippets.
2. Add body-size and timeout hardening at nginx/systemd/container level.
3. Add backup automation scripts and restore verification notes.
4. Add structured JSON logging for production observability.
5. Add a read-only `/status` endpoint for authenticated operational checks.

## 2026-06-27 - Phase 1G Human Behavior Learning

### Completed

- Added `app/brain/human_learning.py`.
- Added deterministic extraction for:
  - direct/practical communication style
  - nurturing/newborn-learning emotion
  - clever/light humor preference
  - user corrections/instructions
  - knowledge interests such as AGI, human brain, emotion, behavior, internet,
    security, ERP, TODY, business, and humor
- Implemented `behavior_memory.remember_preference()` and
  `behavior_memory.recall_preferences()`.
- Implemented `emotional_memory.remember_emotion()`.
- Updated the learning engine so behavior/emotion signals can be saved even
  when the normal episodic review does not require storage.
- Updated the cognitive loop reply prompt to include learned behavior/style
  preferences separately from task/project memories.
- Added `tests/test_phase1g_human_learning.py`.

### Verified

```bash
cd /var/www/maa.tachy.in
.venv/bin/pytest -q -p no:cacheprovider
```

Result:

```text
30 passed
```

### Current Brain Behavior

The brain now starts learning like a controlled newborn layer:

```text
message -> observe tone/emotion/humor/correction/interests
-> store behavior/emotional memory
-> recall learned preferences into future replies
-> keep safety/approval rules above all style adaptation
```

### Next Recommended Brain Phase

Start **Phase 1H: Goal & Personality Formation**.

Recommended order:

1. Add persistent goal creation/update APIs and memory-backed goal recall.
2. Add personality profile synthesis from behavior memories.
3. Add contradiction handling for user preferences.
4. Add confidence/decay fields for learned behavior memories.
5. Add feedback commands such as "remember this", "forget this", and
   "correct your behavior".

## 2026-06-27 - Phase 1H Goal, Personality, and Safe TODY Conversation

### Completed

- Implemented real goal memory in `app/memory/goal_memory.py`.
- Added goal creation/listing routes:
  - `POST /goals`
  - `GET /goals`
- Added personality synthesis in `app/brain/personality.py`.
- Updated `/behavior-patterns` and added `/personality` to expose learned
  personality traits from behavior memories.
- Added explicit feedback command handling in `app/brain/feedback.py`:
  - `remember this: ...`
  - `forget this: ...`
  - `correct your behavior: ...`
  - `set goal: ...`
- Integrated feedback command trace into the cognitive loop response.
- Added safe TODY conversation support:
  - `GET /tody/messages`
  - `POST /tody/reply/draft`
  - `POST /tody/reply/latest`
- TODY reply drafting reads/processes messages and queues an approval-gated
  reply. It does not send automatically.
- Added `tests/test_phase1h_goals_tody.py`.

### Verified

```bash
cd /var/www/maa.tachy.in
.venv/bin/pytest -q -p no:cacheprovider
```

Result:

```text
35 passed
```

### TODY Conversation Behavior

Current behavior is intentionally supervised:

```text
TODY inbound message
-> brain processes message
-> draft reply generated
-> send_message approval requested
-> nothing sent until approval is approved and execute endpoint is called
```

This means Rohit can talk to the brain through its TODY account after live
credentials/deployment are approved, but automatic outbound replies remain
blocked by the approval layer.

### Next Recommended Brain Phase

Start **Phase 1I: Conversational Identity & Dialogue Memory**.

Recommended order:

1. Add conversation/session memory so multi-turn TODY/chat context is retained.
2. Add message direction/author tracking for TODY conversations.
3. Add "who am I talking to" relationship memory.
4. Add supervised auto-reply mode flag, still disabled by default.
5. Add queue/status APIs for pending drafted replies.

## 2026-06-27 - Phase 1I Conversational Identity & Dialogue Memory

### Completed

- Added Rohit's trusted TODY identity to config:
  - name: `Rohit Kumar`
  - username: `rohitsingh`
  - email: `rohitji.patna@gmail.com`
- Implemented real relationship memory in `app/memory/relationship_memory.py`.
- Added guardian sender verification by username/email/name.
- Added dialogue memory in `app/memory/dialogue_memory.py`.
- TODY inbound/drafted outbound turns are now remembered with conversation ID,
  direction, channel, and related person where known.
- Added pending TODY reply status:
  - `GET /tody/reply/status`
- Added verified-guardian direct reply endpoint:
  - `POST /tody/reply/guardian-direct`
- Guardian direct reply verifies Rohit first, then approves and executes only
  the exact generated payload through the existing payload-bound send path.
- Non-guardian TODY replies remain approval-gated.
- Added `tests/test_phase1i_dialogue_guardian.py`.

### Verified

```bash
cd /var/www/maa.tachy.in
.venv/bin/pytest -q -p no:cacheprovider
```

Result:

```text
40 passed
```

### Rohit TODY Conversation Policy

```text
if sender username/email/name matches trusted Rohit profile:
    treat as guardian conversation
    remember dialogue context
    allow guardian-direct endpoint to send reply through verified exact payload
else:
    draft reply only
    require approval before sending
```

No live TODY message was sent during this phase; tests monkeypatch the sender.

### Next Recommended Brain Phase

Start **Phase 1J: Conversation Sessions & Identity Continuity**.

Recommended order:

1. Add explicit conversation/session table or memory index.
2. Add conversation summaries after N turns.
3. Add identity continuity prompt: "I am TACHY Cognitive AI speaking with Rohit."
4. Add supervised auto-reply mode switch, disabled by default except verified
   guardian channels.
5. Add replay-safe message IDs so the same inbound TODY message is not processed
   twice.

## 2026-06-27 - Phase 1J Conversation Sessions & Identity Continuity

### Completed

- Added `TODY_SUPERVISED_AUTO_REPLY=false` config flag.
- Added replay-safe TODY message tracking in `app/memory/dialogue_memory.py`.
- Added processed-message keys so the same TODY inbound message ID is not
  processed twice.
- Added conversation summary generation from recent dialogue turns.
- Added identity continuity context:
  - "You are TACHY Cognitive AI continuing a TODY conversation with Rohit Kumar"
    when sender is verified guardian.
- Updated cognitive loop to accept optional conversation context and include it
  in the LLM prompt.
- Updated TODY message processing to pass message IDs and session context.
- Added `GET /tody/conversation/status`.
- Added `message_id` support to TODY draft/direct reply APIs.
- Guardian direct reply remains verified by username/email/name and now also
  uses replay protection.
- Added `tests/test_phase1j_sessions.py`.

### Verified

```bash
cd /var/www/maa.tachy.in
.venv/bin/pytest -q -p no:cacheprovider
```

Result:

```text
46 passed
```

### Current TODY Conversation Safety

```text
incoming TODY message with message_id
-> reject if already processed
-> verify sender identity
-> store inbound turn
-> build conversation identity/context
-> brain drafts reply
-> store draft outbound turn
-> mark message_id processed
-> queue approval or direct-send only for verified guardian path
```

`TODY_SUPERVISED_AUTO_REPLY` is disabled by default.

### Next Recommended Brain Phase

Start **Phase 1K: Real Conversation Worker Design**.

Recommended order:

1. Add a safe poller design document for reading TODY messages periodically.
2. Add dry-run poller function that reads conversations but sends nothing.
3. Add one-message-at-a-time processing lock.
4. Add operational `/status` for worker health and queue counts.
5. Only after explicit approval, wire a supervised worker process.

## 2026-06-27 - Phase 1K Real Conversation Worker Design

### Completed

- Added `TODY_WORKER.md` with safety rules and activation requirements.
- Added manual TODY worker module: `app/agents/tody_worker.py`.
- Added one-message-at-a-time in-process lock.
- Added dry-run poller that reads conversations/messages and reports the latest
  unprocessed candidate without drafting or sending.
- Added process-once mode that processes one unprocessed message through the
  existing TODY reply pipeline.
- Added worker status counters and last-result state.
- Added API routes:
  - `GET /tody/worker/status`
  - `POST /tody/worker/dry-run`
- Added `tests/test_phase1k_worker.py`.

### Verified

```bash
cd /var/www/maa.tachy.in
.venv/bin/pytest -q -p no:cacheprovider
```

Result:

```text
50 passed
```

### Why TODY Still Does Not Auto-Reply

The code path exists, but no live worker is running. To make the brain reply on
TODY, one of these must happen:

1. Manually call the authenticated TODY reply endpoint.
2. Manually call `POST /tody/worker/dry-run` with `dry_run=false`.
3. After explicit approval, install/run a supervised background worker.

No nginx, systemd, cron, supervisor, or live worker was enabled in this phase.

### Next Required Operational Step

Before live TODY replies can work:

1. Confirm `.env` has valid TODY credentials.
2. Confirm the FastAPI app is running.
3. Confirm `INTERNAL_API_KEY` is known to the caller.
4. Call `GET /tody/connect` to verify login.
5. Call `POST /tody/worker/dry-run` first with `dry_run=true`.
6. Only then call `dry_run=false` or approve a real worker.

### Next Recommended Phase

Start **Phase 1L: Live TODY Activation Checklist**.

Recommended order:

1. Add an explicit activation script that performs read-only preflight checks.
2. Add a no-send smoke test endpoint for TODY credentials.
3. Add a documented manual command to process exactly one message.
4. Add service template but do not enable it without approval.

## 2026-06-27 - Phase 1L Live TODY Activation Checklist

### Completed

- Added activation module: `app/agents/tody_activation.py`.
- Added config/readiness preflight:
  - `GET /tody/activate/preflight`
  - optional `?check_login=true` for a real TODY login check
- Added manual one-message activation endpoint:
  - `POST /tody/activate/process-one`
- Default preflight performs no TODY network call.
- Manual process-one delegates to the locked worker and processes at most one
  message.
- Updated `TODY_WORKER.md` with exact curl commands and a disabled systemd
  template.
- The service template is documentation only. No loop script/service was
  created or enabled.
- Added `tests/test_phase1l_activation.py`.

### Verified

```bash
cd /var/www/maa.tachy.in
.venv/bin/pytest -q -p no:cacheprovider
```

Result:

```text
54 passed
```

### Current Manual Activation Sequence

```text
1. GET  /tody/activate/preflight
2. GET  /tody/activate/preflight?check_login=true
3. POST /tody/activate/process-one {"dry_run": true}
4. POST /tody/activate/process-one {"dry_run": false}
```

This still requires the FastAPI app to be running, valid `.env` TODY
credentials, and `X-API-Key`.

### Why It May Still Not Reply Live

The code is ready for manual activation, but no background worker exists. If no
one calls `/tody/activate/process-one`, the brain will not poll TODY or reply.

### Next Recommended Phase

Start **Phase 1M: Runtime Operator Script**.

Recommended order:

1. Add a CLI script that calls preflight and process-one safely.
2. Add a loop mode that is dry-run by default.
3. Keep live loop disabled unless explicitly approved.
4. Add logs for each processed message ID.
