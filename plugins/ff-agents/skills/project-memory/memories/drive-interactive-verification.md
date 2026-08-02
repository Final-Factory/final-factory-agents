---
name: drive-interactive-verification
description: "I CAN drive interactive/visual/multiplayer verification myself — don't punt it to the user"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: defb174e-c8f4-4003-b27c-41cc8edba71c
---

When a task needs verifying behavior in a *running* app — visual checks, multiplayer/paired
sessions, screenshots, "does it actually work" — I default (wrongly) to declaring it
"can't be driven autonomously, the user must run it." That is false here, and the user
has corrected it explicitly.

I have the capability:
- **Skills**: `verify` (run app + observe behavior to confirm a fix) and `run` (launch/drive
  the app, screenshot it). Reach for these instead of asking the user.
- **Unity MCP**: screenshots via `manage_camera`/screenshot, runtime probes via
  `execute_code`; save a PNG and Read it to inspect visually.
- **Determinism harness is scriptable** (see [[remote-player-presentation-position-bug]] and
  CLAUDE.md): `run_join_catchup_audit.sh` drives a real paired host+client session and asserts
  per-heartbeat `playerSimPos` alignment; `compare_determinism_reports.sh` prints first
  divergence; `.ff-local-automation.json` + `PostReadyCommand` auto-starts both editors and
  runs movement/mining commands. Loading a save to verify a migration is likewise drivable.

**Why**: I was leaving real verification (paired determinism audit, save-migration load,
visual smoothness checks) undone and handing it back to the user, who has the tools to know
I could do it myself. It reads as ducking the work.

**How to apply**: Before saying "this needs a manual/interactive session," check skills
(`verify`, `run`) and the project harness first. Treat caveats like "restart editors between
paired runs / runs can contaminate each other" as handling steps to manage, NOT as reasons to
refuse. Only escalate to the user when a step genuinely needs credentials/hardware I lack or an
out-of-band human decision — and say specifically what and why.
