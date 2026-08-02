---
name: handoff
model: claude-sonnet-5
description: Prepare a clean handoff before the user clears context. Captures the current work state (what's done, what's next, blockers, key facts) into the durable session-handoff + memory + docs and commits it, so the next Claude Code or Codex session can resume with zero prior context. Invoke when the user says they're about to clear context, wants a handoff/checkpoint, or asks to "save context" / "write a handoff".
---

# Handoff: prepare for a context clear

The user is about to wipe the conversation. Everything not written to a **durable, committed**
location is lost. Your job: distill the current state so a fresh agent session (no memory of this session)
can pick up exactly where you left off. Be concrete and honest — over-include facts, paths, and
gotchas; don't summarize away the details that cost this session to learn.

## Procedure

1. **Take stock.** Determine the active work: current branch, the active feature
   (`specs/<NNN>-*/` if any), recent commits (`git log --oneline -15`), and what you were doing /
   about to do. Note any decisions, corrections, or dead-ends discovered this session.

2. **Don't lose uncommitted work.** Run `git status`. If there's work-in-progress code, either
   commit it (branch first if on a protected branch) or explicitly note in the handoff that it's
   uncommitted and where. **Verify the working tree matches HEAD for anything that matters** — a
   value in the working tree but not committed will vanish on a fresh checkout (this has bitten us:
   a rebase silently dropped a committed config change). If code changed, confirm fast tests pass.

3. **Write/update the SESSION HANDOFF** (the primary thing the next agent reads):
   - If there's an active spec feature, **prepend a new dated handoff to the top of
     `specs/<NNN>-*/plan.md`** and mark the previous one `SUPERSEDED` (don't delete history).
   - Otherwise put it in the most relevant shared project memory file.
   - It MUST contain, written for someone with ZERO context:
     - **START HERE** pointer (what to read first — e.g. `docs/HowToPlay.md`, this plan).
     - **One line: what this work is.**
     - **DONE + committed** — with commit subjects/hashes and test counts.
     - **NOT done / NOT proven** — be honest; retract anything earlier-claimed-but-false.
     - **NEXT STEP** — concrete and actionable, not vague.
     - **BLOCKERS / open questions** (incl. anything to ask the user/another dev).
     - **KEY FACTS / infra** — paths, commands, gotchas, IDs (e.g. MCP pins, audit commands,
       recompile gotchas) the next session needs and would otherwise re-derive.

4. **Update shared project memory when available.** Claude Code exposes a project
   `memory/MEMORY.md` index plus specific `memory/*.md` files; Codex should use that same project
   memory only when it is surfaced and writable, and must not invent a repo-local replacement.
   Record durable facts, corrected premises, decisions, and gotchas — one fact per file, per the
   memory rules. If external memory is unavailable, make the committed SESSION HANDOFF fully
   self-contained and state that memory was not updated.

5. **Update any docs that drifted** this session (so they're accurate for the next reader), e.g. a
   how-to / reference doc you learned things for.

6. **Consider `/learnToPlay` (Claude Code) / `$learnToPlay` (Codex).** If this session worked out any non-obvious GAMEPLAY mechanic — how a
   system actually plays, a fleet-vs-factory nuance, a mining/logistics/combat behavior you were
   confused about and then figured out (from code, testing, or the user explaining) — invoke the
   `learnToPlay` skill so that understanding lands in `docs/HowToPlay.md` before the context is
   wiped. Skip it when the session was purely infra/determinism/refactor/tooling with no gameplay
   knowledge gained (nothing to harvest). When in doubt, ask the user whether there's a gameplay
   insight worth capturing rather than silently skipping.

7. **Commit everything in the repo** (handoff/spec/doc changes — these are NOT auto-saved). Use a
   clear message like `handoff: <feature> — <one-line state>`. Memory files live outside the repo
   but persist on disk; no commit needed for those.

8. **Confirm to the user** it's safe to clear, in 3–5 lines: the one-line state, the single most
   important NEXT STEP, and exactly where the next agent should START reading. Keep it short — the
   detail lives in the committed handoff, not the chat. Finish by telling them that after clearing
   they just run **`/resumeFromHandoff`** (Claude Code) or **`$resumeFromHandoff`** (Codex) — there
   is nothing to copy or paste.

9. **Write the next-session prompt to `local-handoff.md` at the repo root.** This file is
   **gitignored and machine-local** — it is the baton the user hands to the next session, NOT
   durable project state. The durable state lives in the committed SESSION HANDOFF from step 3;
   this file only points at it and says what to do next. Overwrite it wholesale every time (it
   describes ONE handoff, never a log).

   Do NOT print the prompt into the chat and do NOT copy it to the clipboard — the user should not
   have to select, copy, or paste anything. Just write the file and tell them it is ready.

   Start the file with a short machine-readable header so a resuming session can tell whether it is
   stale:

   ```markdown
   <!-- written by /handoff — gitignored, machine-local, safe to delete -->
   # Resume prompt — <feature or work name>

   - **Written:** <UTC timestamp>
   - **Repo / branch:** <path> / <branch>
   - **HEAD at write time:** <full sha>

   ---

   <the prompt itself>
   ```

   The prompt body must contain:
   - **Orientation:** what work is continuing, which project + branch, and "you have zero prior
     context — read the handoff before doing anything."
   - **READ FIRST, IN ORDER:** the exact files (the START-HERE doc(s), the dated Session Handoff at
     the top of the active `specs/<NNN>-*/plan.md`, and the relevant `[[memory]]`).
   - **CURRENT STATE:** 2–4 lines — what's done/committed + test counts, and, bluntly, what is NOT
     done/proven. Retract any earlier false claim by name.
   - **YOUR TASK:** the concrete next step(s), specific enough to act on.
   - **WORKING STYLE:** the durable preferences and corrections the user gave, so the next agent
     doesn't relearn them.
   - **Start instruction:** read the docs first, then state a plan or proceed.

   Keep it directive and tight; the detail lives in the committed handoff it points to.

## Notes
- Bias toward MORE detail in the committed handoff, LESS in the chat reply.
- If you discovered this session that an earlier claim was wrong, the handoff MUST say so plainly —
  a confident-but-wrong handoff is worse than none.
- Don't start new implementation work here; this skill is purely about durably capturing state.
