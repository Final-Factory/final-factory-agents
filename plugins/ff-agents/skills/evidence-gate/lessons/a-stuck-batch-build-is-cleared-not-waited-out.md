---
name: a-stuck-batch-build-is-cleared-not-waited-out
description: "A worker whose Unity start is refused because a -batchmode build holds the slot asks the daemon to clear it (mcp__machine__unity action clear_batch), reads why a build stays, and never waits hours or asks a person to end it. A worker that starts a batch build runs it under unity-slot run and leaves none behind."
date: 2026-10-09
---

# A stuck batch build is cleared by the daemon, not waited out and not ended by hand

**Rule.** When `mcp__machine__unity` refuses a start because every Unity slot is full and the
refusal (or `unity-slot status`) names a `-batchmode` build that holds the slot for more than an
hour, call `mcp__machine__unity` with `action: "clear_batch"`. The daemon's reaper
(`machine/unityReaper.ts` in FF Factory) ends the sandboxes' batch builds whose owner is gone (10 min
without log or CPU progress, or 90 min old) or that are hung (owner alive, an hour old, 30 min without
progress), removes the stale `Temp/UnityLockfile`, and says for every build it keeps why it keeps it.
A build kept as healthy is waited on with `wake_me`; the limits do not move on request. The hook
refuses ending Unity by hand and no person should have to approve it: the tool is the way.

A worker that starts a batch build (`Unity -batchmode -executeMethod …`) runs it under `unity-slot run`
(the game repo's build scripts already do), gives it a `-logFile` (the reaper reads the log's growth as
progress), and checks `unity-slot status` for its own builds before it reports DONE.

**Why.** 2026-10-09 (w791): twice, a batch build held a sandbox's Unity slot for hours until a person
approved ending it by hand through the ops worker. LothDesktop pid 3856, a nightly prepare build of
slot4, hung 209 min on "More than one copy of bee_backend running in slot4" with its script alive and
blocked w769's worker (the Steam Deck hint draw-order fix); m5 pid 81390, a worker's Mac build, was 15 h
old with parent pid 1. Workers cannot end Unity, so both waited for a person. Ben's rule: the harness
learns from a repeated problem.

**How to apply.**

- A start refused for a batch holder: `clear_batch` once, read the answer, then `wake_me` only for a
  build it called healthy. An answer of "protocol 8 … cannot clear" means the daemon is old: say so in
  the report and let the orchestrator ask for the deploy.
- Measured on 15 healthy nightly builds (4.5 to 36.9 min, median 8.4), so a build under an hour old is
  never judged hung; do not report one as stuck before then.
- Do not start a batch build in a sandbox whose interactive editor runs (two copies of bee_backend lock
  each other); stop the editor first (`unity stop`).
- FF Factory side: `docs/unity-lifecycle.md`, "Orphaned and hung batch builds are ended".
