# Shree — AI Coding Agent (`shree`)

Shree is a plan-first, tool-using coding agent for your terminal — like Codex /
Claude Code, but she's *your* Shree, with security, guardrails, and audit built
in. She reviews your approach before writing code, warns you about mistakes and
risks, and never leaks secrets or runs forbidden commands.

## Quick start

```bash
shree "add rate limiting to the login endpoint"   # plan → you approve → she does it
shree                                              # interactive REPL
shree --plan "refactor the fee module"             # plan + approach review only
shree --auto "fix the failing test"                # auto low-risk edits, ask on risky
shree --yolo "..."                                 # execute without asking (git-checkpointed)
shree -C /path/to/repo "..."                       # run in another repo
```

## How she works (plan-first)

1. **Plan** — she reads enough of your repo, **reviews your approach, flags
   mistakes and risks, and proposes options** — then *waits for your OK*. When
   there's a real design choice she gives 2-3 options with tradeoffs, a
   recommended pick, and an honest confidence %. This is "correct my mistakes
   before you implement."
2. **Execute** — she runs a tool loop (read / grep / edit / write / bash /
   tests), taking a **git checkpoint before every edit** so any change is
   revertible.
3. **Verify** — she runs the tests; on failure she reads the error and fixes it
   (bounded), only finishing when they pass.
4. **Self-review** — she critiques her own diff (with a confidence score) before
   declaring done.
5. **Risk report** — she prints what changed, the highest risk tier reached, and
   every alert raised, so you know exactly what to review.

## Security (defense in depth)

Shree classifies every tool call by its **actual arguments** into a risk tier
and enforces it before the tool runs:

| Tier | Examples | Behaviour |
|------|----------|-----------|
| **LOW** | `read_file` on normal code, `ls`, `pytest` | auto-allowed |
| **MEDIUM** | `edit_file`/`write_file` on code, reading `.env` (values redacted) | proceeds, logged |
| **HIGH** | edit `.env`/credentials/keys, `git push`, `drop table`, `curl`, `rm -rf build/` | needs Rohit's approval |
| **FORBIDDEN** | `rm -rf /`, `mkfs`, `dd of=/dev/`, `shutdown`, fork bomb, `curl \| sh` | **blocked, no approver can override** |

- **Secret redaction** — every file read, grep match, shell output, and
  `git diff` is scanned for keys, DB URLs, private keys, and `.env` values and
  **redacted before** it reaches the LLM or your terminal. Reading `.env`
  returns the key names with values hidden, so she can see structure without
  ever leaking a secret. `cat .env` over bash is redacted too.
- **Prompt-injection guard** — file contents and command outputs are scanned for
  "ignore previous instructions"-style payloads; high-severity injection lines
  are **quarantined** so a malicious README or comment can't hijack the model.
- **Sandbox** — paths are confined to the target repo (no `..`, no symlink
  break-out, no absolute paths outside the root).
- **Forbidden commands never run**, even in `--yolo` with an approver saying yes.

## Guardrails ("warn me")

During execution Shree raises live alerts (printed in red) and a final risk
report for:

- **Secrets redacted** — count per call and total, so you know a secret was
  encountered and hidden.
- **Prompt injection quarantined** — count of blocked injection attempts.
- **Scope drift** — editing a file that wasn't in the approved plan's
  `files_to_touch`.
- **Over-engineering** — changing far more files than the plan expected.
- **Low-confidence self-review** — if her own review confidence is < 60%, she
  tells you to double-check the diff before trusting it.
- **Audit degradation** — if the audit DB is unavailable, she says so (and falls
  back to a file log).

## Audit

Every tool call is audited (`coding_tool_call`) with its tool, args (secrets
redacted), result, and risk tier — not just the run summary. Blocked and denied
actions are audited too. If the DB is down, audits are appended to
`storage/logs/audit_fallback.log` so the trail is never silently lost.

## Safety

- Destructive commands (`rm -rf`, `git push`, `drop database`, `curl | sh`, …)
  always need approval, even in `--auto`; forbidden commands never run.
- Every edit is a scoped git checkpoint of *only that file* (Rohit's unrelated
  working-tree changes are never swept in): `git diff` to review,
  `git reset --hard HEAD~1` / `git checkout .` to undo.

## Model & tokens

- **NVIDIA Nemotron (default)** — works with no extra key. The coding loop uses
  a small reasoning budget so it's snappy, an adaptive completion budget (smaller
  for simple tasks), transcript compaction, and **reuse of plan-time reads** so
  she doesn't re-read files and waste tokens/round-trips.
- **Claude (optional, sharper)** — add `CODING_ANTHROPIC_KEY=sk-ant-...` and
  `CODING_MODEL=claude-sonnet-5` to `.env` for the best agentic tool-use.
- `CODING_AUTONOMY=plan_first` (recommended default). Override per-run with
  `--auto` / `--yolo`.
- `CODING_VERIFY=true` runs the repo's tests before "done"; set
  `CODING_TEST_COMMAND` to override auto-detection.

## Reliability

- **Repo grounding** — she detects languages, test command, and conventions and
  plans against the real repo.
- **Verify → fix → retry** — she runs your tests and fixes failures (bounded).
- **Self-review with confidence** — she critiques her diff before declaring done.
- **Stuck-detection** — if she repeats a failing step she *stops and asks*
  instead of thrashing to the step limit.
- **Clean history** — all in-run checkpoints collapse into one staged diff.
- **Telemetry** — every run reports steps, ~tokens, time, and max risk tier.
