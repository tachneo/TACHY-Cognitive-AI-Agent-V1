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
