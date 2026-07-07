# Shree — AI Coding Agent (`shree`)

Shree is a plan-first, tool-using coding agent for your terminal — like Codex /
Claude Code, but she's *your* Shree, with memory and safety built in.

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
   mistakes and risks**, and proposes steps — then *waits for your OK*. This is
   "correct my mistakes before you implement."
2. **Execute** — she runs a tool loop (read / grep / edit / write / bash /
   tests), taking a **git checkpoint before every edit** so any change is
   revertible.
3. **Verify** — she runs the tests and reports honestly what changed and how she
   checked it.

## Safety

- Sandboxed to the target repo (no path escape, no touching your wider system).
- Destructive commands (`rm -rf`, `git push`, `drop database`, `curl | sh`, …)
  always need approval, even in `--auto`.
- Every edit is a git commit checkpoint: `git diff` to review, `git reset --hard
  HEAD~1` to undo the last step.
- Full audit log in the brain.

## Model

By default Shree codes with **Claude** (best agentic coding + tool use). Add your
key to `.env`:

```
CODING_ANTHROPIC_KEY=sk-ant-...
CODING_MODEL=claude-sonnet-5     # or claude-opus-4-8 for the hardest work
```

Without a Claude key she falls back to your current provider (NVIDIA Nemotron),
so she works today — Claude just makes her sharper.

## Autonomy default

`CODING_AUTONOMY=plan_first` (recommended). Override per-run with `--auto` /
`--yolo`.

## Reliability (P0 hardening)

Shree is engineered to be *trusted*, not just to demo:

- **Repo grounding** — she detects your languages, test command, and
  conventions and plans against the real repo.
- **Verify → fix → retry** — she doesn't accept "done": she runs your tests,
  and if they fail she reads the error and fixes it (bounded), only finishing
  when they pass. `CODING_VERIFY=true` (set `CODING_TEST_COMMAND` to override
  detection).
- **Self-review** — she critiques her own diff for bugs/omissions before
  declaring done.
- **Stuck-detection** — if she repeats a failing step she *stops and asks*
  instead of thrashing to the step limit.
- **Clean history** — all in-run checkpoints collapse into one staged diff:
  `git diff` to review, `git checkout .` to discard.
- **Telemetry** — every run reports steps, ~tokens, and time.

## Model & speed (important)

Coding quality and speed depend on the model:

- **Claude (recommended for real work)** — add `CODING_ANTHROPIC_KEY=sk-ant-...`.
  Fast, best agentic tool-use. `CODING_MODEL=claude-sonnet-5` (or
  `claude-opus-4-8` for the hardest tasks).
- **NVIDIA Nemotron (default fallback)** — works with no extra key, but it's a
  slow reasoning model (~30s per step), so multi-step tasks take several
  minutes. Fine for small/async tasks; add the Claude key for snappy
  interactive work. `CODING_NVIDIA_REASONING_BUDGET` trades quality for speed.
