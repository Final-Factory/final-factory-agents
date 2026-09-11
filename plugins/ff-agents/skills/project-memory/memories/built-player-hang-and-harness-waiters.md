---
name: built-player-hang-and-harness-waiters
description: "A shell-launched built player can hang forever at waiting-title-menu at 0.2% CPU (kill the path-verified PID, relaunch); the Claude harness kills run_in_background waiters under memory pressure, so long waits go through Monitor."
---

# Built-player boot hang and harness background waiters (2026-09-11)

**Boot hang.** The M5 tutorial host (`finalfactory.app` launched by `launch-host.sh`, pid 3099)
sat 25 minutes at status `waiting-title-menu` with `Entity Prefab Container not yet created,
deferring game initialization...` printed three times, process state `SN` at 0.2% CPU, log
mtime frozen at launch. `runInBackground` is 1 in ProjectSettings, `osascript activate` hung
(the app did not answer Apple events), so it was a genuine stall, not a paused player. It
coincided with a system low-memory moment (two editors in play with 4096-record dumps plus a
2.5 GB scp). Recovery that worked: verify `ps -o command= -p <pid>` shows the run root's app,
kill it, move `host-terminal.log` aside (the launch script refuses an existing log), relaunch
— the second boot loaded the save in 13 s. A healthy boot prints that "deferring" line ~50
times within seconds and moves on.

**Harness waiters.** `run_in_background` Bash commands that poll with `sleep` are killed by
the Claude harness with "stopped because the system is running low on memory" whenever an
editor build or play session spikes memory — three waiters died mid-leg this way. Use the
`Monitor` tool with an `until <check>; do sleep N; done` loop for anything that outlives a
minute; it survived every spike. Foreground `sleep` is blocked outright.
