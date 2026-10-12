---
name: a-wait-is-a-harness-timer
description: "A poll or a wait that must outlive the turn is the harness's: wake_me (one check-in), blocked_on (another request, a PR, CI, a deploy), set_timer (orchestrators and the ops worker: every N minutes, until, max_fires), waiting_on_person (a person). Never a background shell loop, a sleep loop, nohup or & or a Monitor: the agent's process ends at an idle reap, a sandbox release or (for the portal's own agents) every portal deploy and restart, and the loop dies with it, silently. w1070's idle poll died at the first deploy after one check (w1106)."
date: 2026-10-12
---

# A wait is a harness timer, never a background loop

**Rule.** When something must be checked again after your turn ends (a machine going idle, a build, an import, CI,
another request), hand the wait to FF Factory, which keeps it on the portal:

| Waiting for | Use | Survives a portal restart and a daemon update because |
|---|---|---|
| a time (an import, a build, a reboot to come back) | `wake_me` (one, a person's message cancels an orchestrator's) | kept in `data/wakes.json`, re-armed at the portal's start (`Waker.restore`); one due meanwhile fires at once |
| another request, a PR's merge, CI on your PR, a deploy | `blocked_on` | stored on the request (`WorkItem.blocked`); `BlockerWatch` looks again at every start |
| a standing check ("every 2 h for 3 days, then act") | `set_timer` (orchestrators and the ops worker) | kept in `data/timers.json`; a fire due meanwhile is delivered once, with the missed count |
| a person | `waiting_on_person` ([lesson](a-person-wait-is-declared-not-polled.md)) | it is the ledger's state, not a timer |

Never a `while`/`until`/`for` loop with `sleep` (or `Start-Sleep`) sent to the background (the Bash tool's
`run_in_background`, `&`, `nohup`, `setsid`), a backgrounded script that loops, or a Monitor, to finish the work after
the turn. A short loop in the foreground, within the turn, is fine.

**Why.** 2026-10-12 (w1106, from w1070: grow LothDesktop's V: once LothDesktop is idle): the ops worker ran its idle poll
as a background Bash loop (`w1070-wait.sh`, every 18 min). The loop lived in the worker's Claude process. That process
is the portal's socket connection, so it ends at every portal deploy and restart, and after a 1-hour idle stop. The
05:33Z deploy killed it after one check, and nothing noticed until lothsahn asked. lothsahn: "Please make sure polls are
done via the timer framework and don't get interrupted by portal updates." A sandbox worker has the same gap. Its
process keeps running across a portal restart and a daemon update (w605), but the reaper stops an idle worker after an
hour, and a sandbox released for other work ends it too. A loop that finds its condition after the turn wakes nobody.

**How to apply.**

- Before you end a turn with something left to check, name the harness tool that brings you back. "A background task
  is watching it" is not one.
- The note of a `wake_me` or a timer stands alone: the exact command, the condition, the action when it is met
  (only what the person already approved for that request), and what to report. A timer's fire may open a fresh
  conversation.
- When the condition is met or the request closes, cancel what you set (`cancel_wake`, `cancel_timer`).
- The ops worker's guard refuses a backgrounded loop or sleep, in the command or in a scratch script it runs
  (ff-factory `pollProblem`, `server/opsWorker.ts`; docs/ops-worker.md, "Polls and waits: timers").
