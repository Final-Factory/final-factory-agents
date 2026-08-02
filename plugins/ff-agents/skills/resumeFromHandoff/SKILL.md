---
name: resumeFromHandoff
description: Resume work after a context clear by reading the machine-local `local-handoff.md` that /handoff wrote. Use when the user says "resume", "pick up where we left off", or invokes this right after clearing context — it replaces copy-pasting a next-session prompt.
---

# resumeFromHandoff

Pick up exactly where the previous session left off. `/handoff` wrote a resume prompt to
**`local-handoff.md`** at the repo root (gitignored, machine-local). Read it and follow it.

**Invocation**: `/resumeFromHandoff` (Claude Code) · `$resumeFromHandoff` (Codex).

## Procedure

1. **Read `local-handoff.md` at the repo root.**

   If it does not exist, do NOT guess. Say so, then offer the fallbacks in order:
   - the dated `SESSION HANDOFF` at the top of the active feature's `specs/<NNN>-*/plan.md`
     (find the feature via `.specify/feature.json` if present),
   - the project memory index (`MEMORY.md`) for an `ACTIVE` pointer,
   - `git log --oneline -15` plus `git status` to infer recent work.
   Ask the user which to use rather than inventing a task.

2. **Check whether it is stale.** The file header records the branch and the HEAD it was written
   at. Compare against the current branch and `git rev-parse HEAD`:
   - Same HEAD → proceed.
   - HEAD moved → say so explicitly and note that commits landed since it was written (this repo
     has concurrent agents pushing to the shared branch, so this is normal). Skim
     `git log --oneline <written-sha>..HEAD` before acting, and treat any claim in the prompt about
     current state as needing re-verification.
   - Different branch → stop and ask. Do not silently apply a handoff from another branch.

3. **Follow the prompt as if the user had just typed it.** Do its READ FIRST list in order, honour
   its WORKING STYLE section, and carry out its task. It is the previous session's instruction to
   you, not background reading.

4. **Verify before you rely on it.** The prompt is a summary written by a session that is now gone.
   Its file:line citations and state claims were true when written. Re-check anything load-bearing
   against the actual code and `git status` before building on it — especially "X is done" and
   "Y is not done".

5. **Do not delete or edit `local-handoff.md`.** It is overwritten wholesale by the next `/handoff`.
   Leaving it costs nothing and preserves the trail if the resume goes sideways.

## Why this exists

The durable record is the committed SESSION HANDOFF in the repo; `local-handoff.md` is only the
baton — a machine-local pointer saying "read that, then do this". It is gitignored deliberately:
it describes one moment on one machine, it would conflict constantly between concurrent agents,
and it must never be mistaken for project state.

Companion skill: `handoff` (writes the file). Together they remove the copy-paste step — the user
runs `/handoff`, clears, then runs `/resumeFromHandoff`.
