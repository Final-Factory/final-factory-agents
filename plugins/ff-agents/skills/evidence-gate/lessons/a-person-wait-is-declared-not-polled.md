---
name: a-person-wait-is-declared-not-polled
description: "Never hand a person a machine step you or the harness's own tools can do: closing or opening Unity (a person's editor on a main clone included: close it cleanly, do the work, reopen it), git commands, copying files, an installer rerun or a daemon update (the ops worker). A person is asked only for what the rules reserve. A worker that needs a person to act (reboot, log in, decide, approve, hand over a secret) declares it with FF Factory's waiting_on_person tool, names who and what in its report and its 'wNNN: still open:' line, and ends its turn. It never polls for a person with wake_me: a pending check-in makes the ledger show the request Working. A wait on a machine or a job that must outlive the turn is a harness timer (wake_me, blocked_on, set_timer), never a background shell loop, sleep loop, nohup, & or Monitor: the process ends at an idle reap, a sandbox release or a portal deploy, and the loop with it (w1106)."
date: 2026-10-10
---

# A wait on a person is declared, never polled

**First, check that a person is really needed (w855, w935).** Never hand a person a machine step you, the
harness's tools or the ops worker can do. That covers closing or opening Unity, git commands, copying a file or a
save, and an installer rerun. A person is asked only for what the rules reserve to them: approvals, design decisions,
spending, publishing, and admin acts that need their own words (money, deleting, releases, app settings, a secret), or
a physical act (reboot, login). The wider rule, for anything you would call impossible or hand back (w1287: a Claude
Design project "can't" be made while Ben's m5 was signed in to claude.ai): [research the route, then try it or file
it](research-the-route-before-you-say-cant.md).

- **An editor open on a project you must change** (your sandbox's, or a machine's main clone, a person's own project
  folder included): you close it cleanly, do the work, and reopen it if a person was using it. Save its scenes first
  (`EditorSceneManager.SaveOpenScenes()` through the bridge), or copy the unsaved scene files to a backup folder and
  say where. Then quit it (`mcp__machine__unity stop` in a sandbox; elsewhere `EditorApplication.Exit(0)` through the
  bridge, or `osascript -e 'tell application "Unity" to quit'`; editor-ops `references/recovery.md`), poll until its
  process is gone, change the project, and relaunch it on the same project path. An open editor is a step in your list,
  not a stop sign and not a question for the person. The brief's "leave Unity closed, or say if it was open" means:
  close it if it was open, and say it was.
- **Machine steps** (git, copying, installers) go to the tools: the ops worker (`ops_worker machine_update`, or `send`;
  docs/ops-worker.md) or ssh. An installer rerun, a daemon update or a reinstall is the ops worker's, not Ben's or
  lothsahn's. "Update the machines" means every machine's daemon through it, installers included.
- **When the harness itself blocks the step** (the guard refuses a path or a tool; a machine's main clone is open to a
  worker only when its request carries the `main_clone` grant its person's orchestrator set, w936, editor-ops): say which tool refused what, and
  hand that step to the requester's orchestrator (a `decide_work` note) for the ops worker or ssh. Never write "what Ben
  needs to do" with commands for him to run (w934).

Quotes. lothsahn, 2026-10-10 (from w847, where the dispatcher asked Ben to rerun biscuit's installer): "don't ask ben
to run installers.  Update your instructions.  Stop doing that.  When we say update the machines, do the update,
including installers if necessary". Ben, 2026-10-10 (w935, from w934, where worker b384063a found Unity open on his m5
main clone and stopped with "What Ben needs to do: close Unity... then tell me", git commands included): "Dude, why are
you telling me to close Unity? You can close Unity. There's tons of instructions on how to manage Unity instances. I
can't believe I'm still having to tell you this. The workers are opening and closing and doing whatever they want with
Unity all the time, so I'm sure they can handle it." A tool's refusal ("its sandbox count comes from its installer")
points at the step to send, not at a question. The dispatcher hands the step to the requester's orchestrator in a
`decide_work` note; an orchestrator calls the tool in any turn. Only then declare the wait, below.

**Rule.** When only a person can move you on (they must reboot or log in to a computer, decide,
approve, hand over a secret), call `mcp__machine__waiting_on_person` with `who` and `what`, then end
your turn with a report that names the same person and action and carries a
`wNNN: still open: waiting on <Name> to <do what>` line. The ledger then shows the request
**Waiting on input (on <Name>)**. A `wake_me` check-in is for machines and jobs (CI, a build, an
import); you may set one as a fallback, but never instead of the declaration. Your next message
ends the declaration, so declare again if a person is still needed. A daemon too old to offer the
tool: say it in the still-open line ("(a person)", "waiting for Ben to …"); the ledger reads that
as a backstop.

**Why.** 2026-10-08 (w691, from w665, Ben's Mac GPU page fault): from 01:52 UTC worker d558ba14
needed Ben to reboot and log in to the m3 (FileVault). It set `wake_me` check-ins of 2 h and 6 h and
reported "w665: still open: m3 reboot and login (a person), …". The ledger counts a worker with a
pending check-in as Working, so w665 read Working for about 10 hours while nobody could act and Ben
did not know he was needed. Check-ins are Working on purpose (the worker comes back by itself); a
person does not come back because a timer fired.

**How to apply.**

- Before a `still open:` line that names a person, a computer's physical state or a login, the
  declaration comes first, then the report.
- Waiting on CI, a build, a lock or another request is not this: use the check-in or a
  dispatcher-set blocker (`decide_work block`). The test: would a timer change who must act next?
  If not, it is a person.
- Dispatcher and orchestrators: a worker's report with such a line and no declaration is a worker to
  correct, not a Working request to leave.
- FF Factory side: `docs/orchestrators.md`, "Waiting, Queued, Blocked" (`waiting_on_person`,
  `personWaitIn`).

## Never ask a person what they already answered (w1812)

**Rule.** Before you ask a person anything (a worker's `waiting_on_person`, the dispatcher's `decide_work ask`, an
orchestrator's `ask_person` or relayed `[needs you]`), read the request's notes and log, and those of the other requests
the same worker holds. An answer of theirs given after the question was raised is the answer: use it, pass it on, and do
not ask again. One question that shows on several requests is asked once, and the answer on one is the answer on all.

**Why.** 2026-10-22: worker c28c5061 held w1767 (circuit markers in normal view) and w1768 (the circuit alt mode) and
asked one set of four design questions. They showed as Waiting on input on both. Ben answered on w1767, then was asked
the same four on w1768: "i already answered this why are you asking me in the waiting on input for this still". Earlier,
2026-10-15, w1182 (fog of war): an orchestrator re-asked a stale `[needs you]` from a stopped worker that Ben had already
answered: "i already said it looks good and asked for the fog to be a blueish not just grey".

**How to apply.**

- Before you ask, open the request (`read_work wNNN`, `list_work` with its id) and its worker's other requests. Look
  for a note by that person dated after the question.
- A worker declaring for one of several requests names it (`waiting_on_person` `request`). A question for all of them is
  one declaration with no request, never one per request.
- A `[needs you]` that says "waits on wNNN too" is ONE question: ask it once and record the answer on the request it
  came on.
- FF Factory enforces it since w1812: one `[needs you]` per shared question; an answer on any of those requests answers
  all of them; no `[needs you]` when the answer is already logged; `ask_person` and `decide_work ask` refuse a repeat once,
  with the person's words (ff-factory `docs/orchestrators.md`, "Questions for a person"). A refusal from them is the
  answer: pass it on.

## A decided UI change gets no look OK (w2084)

**Rule.** Before you raise any question for Ben (or any person), read every note of theirs on the request and on its
related requests, from the start, not only those after your last question. A new question whose answer follows from
what they already decided is not asked. A UI change whose content they already decided (their wording or behaviour,
added as plain text in an existing component, with nothing else moved) gets no separate look OK: run the UI checks,
quote their decision in the PR, and merge on green. New visuals still need their OK on stills: a new component, a
layout change, art (the [UI checklist](../checklists/ui.md) design gate).

**Why.** 2026-10-24, w1958 (Discord bug sweep), game PR #2395 (the low-ore alert tooltip): Ben decided at 04:59 "Right-click
dismisses for a while; shift+right-click silences for good". The PR added that one line to the existing tooltip. A
fresh session (worker d57b4ea5, started by the "fresh session after a merge" pilot, w2043) took over at 15:52 and asked
"can it merge as it looks?" anyway. Ben: "i already answered this. you keep asking me questions i already answered". The
third time, after w1182 and w1768/w1812 above. The w1812 rule missed it: it reads for an answer given *after* a
question was raised, and this was a new question; FF Factory's repeat check matches the same question, not a decision
that covers a new one. The brief's "New player-visible UI or art needs Ben's OK on stills before merge" and unity-ui's
"put the stills in front of the person who asked" were read as covering a text line he had written himself.

**How to apply.**

- A fresh session reads the request's whole notes and its related requests' notes (`read_work` each) before its first
  `waiting_on_person`; the handover's "Latest" line is not the decisions.
- For a UI question, name the note that decided the content. If it covers the change, the PR's `## Evidence` carries
  `Decided (Ben, <date>): "<his words>"` and the change merges on green with no card.
- Ask only for what the note does not cover, and say in the question what he already decided.

## A wait on a machine is a harness timer, never a background loop (w1106)

**Rule.** When something must be checked again after your turn ends (a machine going idle, a build, an import, CI,
another request), hand the wait to FF Factory, which keeps it on the portal:

| Waiting for | Use | Survives a portal restart and a daemon update because |
|---|---|---|
| a time (an import, a build, a reboot to come back) | `wake_me` (one, a person's message cancels an orchestrator's) | kept in `data/wakes.json`, re-armed at the portal's start (`Waker.restore`); one due meanwhile fires at once |
| another request, a PR's merge, CI on your PR, a deploy, files or results another request's worker makes for you | `blocked_on` (`reports: ["wNNN"]` for that worker's next report, w1841) | stored on the request (`WorkItem.blocked`); `BlockerWatch` looks again at every start |
| a standing check ("every 2 h for 3 days, then act") | `set_timer` (orchestrators and the ops worker) | kept in `data/timers.json`; a fire due meanwhile is delivered once, with the missed count |
| a person | `waiting_on_person` (above) | it is the ledger's state, not a timer |

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
- **Stopping a background task does not stop the script it ran** (w1201, 2026-10-13). TaskStop on a Bash
  `run_in_background` task ended the tool's shell wrapper, and the bench script it had started (`quiet_ab.sh`) kept
  going: it launched LifeSave bench legs and a two-player pair beside the replacement A/B rounds, so four legs ran on
  top of each other and were thrown away. Before a replacement run, list your own processes (PowerShell
  `Get-CimInstance Win32_Process`, `CommandLine` matching your `$TMPDIR` scripts and your player slots) and end the old
  script's tree yourself (`taskkill /T /F /PID <its bash pid>`; never Unity, which goes through `mcp__machine__unity`).
  A timing leg starts only when that list is empty. On Windows, `scripts/bench/quiet_gate.sh` passed at once until
  w1201's #1630 (Git Bash's `ps` has no `-A`), so a gate that returns instantly there is a sign it checked nothing.

## Your own checks are yours: never wait on the orchestrator for them (w1841)

**Rule.** A two-machine or pair check, a determinism check, a player build, a test run and CI on your own pull request
are your own work. Run them yourself. A check that needs two or more computers at once is `mcp__machine__request_pair`
(w1945); ask the dispatcher only for what it alone can give, such as a place on another computer. Never end a turn with `wNNN: still open: waiting on the orchestrator` (or the dispatcher)
to run one of them.

**Why.** 2026-10-23 (w1841, from w1685): worker d582a5da had Ben's go to merge the black-hole swallow (PR #2254). It
ended its turn with "w1685: still open: waiting on the orchestrator to run the two-machine check
`MP-W1685-black-hole-swallow-2p` (black-hole swallow, two peers) on a Windows or Linux pair, then the merge of PR #2254".
No orchestrator runs a worker's check. Nothing set a timer or a gate, so the request showed Stalled in Ben's filter
beside five others that were not stalled either. Ben asked: "why are these stalled?". The request filed for him (w1841): "pair
checks are the worker's own".

**How to apply.**

- Before you write a `still open:` line, name who moves it on. If that is you, do it now. A person is
  `waiting_on_person`. Another request, a pull request or a deploy is `blocked_on`. Files or results another request's
  worker makes for you are `blocked_on` with `reports: ["wNNN"]`, and you are resumed when that worker reports. A time
  is `wake_me`. "The orchestrator" is none of these.
- A two-machine check needs a second machine. Run it from your own sandbox where one computer is enough (the game repo's
  scenario runner and `unity-slot run --count 2`). Where it needs two or more computers at once, call
  `mcp__machine__request_pair` (what, brief, legs, `cross_os` only for w1692's reasons, `timed`): it files one pair request
  whose legs the dispatcher starts together, one free sandbox per computer, and Blocks your request on its report, so your
  sandbox is freed as your turn ends and the host leg's `For wNNN:` line resumes you. The legs talk with `message_pair`.
  Never hold your sandbox waiting for a second machine's worker (w1945, lothsahn: "Can we make the dispatcher smart enough
  so it queues work properly that requires running together across multiple machines and doesn't waste slots?"; w665's
  worker held m3's only sandbox for hours waiting on a Windows pair).
- FF Factory tells a worker that ends its turn this way that the work is its own, once per request
  (ff-factory#554, `Agents.ownWorkNudge`). The ledger's Stalled line says "that is its own work".

## Capacity is never a question (w2147, 2026-10-25)

**The rule.** Workers, dispatchers and orchestrators never ask a person for capacity or a computer. That means no
question to bring a computer online, wake or unpause one, say which computer may run or time the work, allow a computer
the rules already allow, or run an installer or an update on one. Computers come and go: work that no online computer
fits waits **Queued** and starts by itself on the first one that fits, in the timing order (smallest free computer
first, then pre-emption of movable work on a small one, then the queue; a big computer only for high or urgent work, or
when every smaller one is offline). The one exception is a concrete blocker only that person can clear: their own login,
password, FileVault or 2FA code, a reboot of their own machine, an admin prompt. Name that blocker and the smallest step.

lothsahn, 2026-10-25 (w2147, from w1958): "Stop asking to bring computers online. It's a cluster where computers are
sometimes online and sometimes paused. Use and schedule resources based on what you have. Don't ask for permission."

**Why: two cases.**

- **w1958 (2026-10-25).** The worker, on m5 (which takes no timed runs), queued a Windows frame-rate A/B for
  desktop-coosego, which was offline. `timed_place` then answered "no small computer takes w1958's timed leg: ask an
  operator", and the worker put a card in front of lothsahn: "bring desktop-coosego back online, or say which computer
  may time the shield frame-rate A/B". The portal itself suggested the question, so the fix (FF Factory w2147) went into
  the tool as well as the rule: `timed_place` now always files the leg Queued, and `waiting_on_person` and the
  dispatcher's `decide_work ask` refuse a wait whose only ask is a computer.
- **w847 (2026-10-10).** The dispatcher asked Ben to rerun biscuit's installer. lothsahn: "don't ask ben to run
  installers.  Update your instructions.  Stop doing that.  When we say update the machines, do the update, including
  installers if necessary". This lesson treats it as the first correction of the same kind (a machine's state handed
  to a person), so w1958 was the second, and the second gets a tool check
  (the first section above).

**How to apply.**

- **Timed work**: `timed_run` queues for its computer and goes out by itself when that computer is back; `timed_place`
  files the leg Queued even when nothing fitting is online. Never wait for one named computer when another that takes
  timed runs fits. The exclusions stand: m5 takes no timed runs.
- **A check on several computers**: `request_pair`, which waits for them by itself.
- **Anything else that needs a computer that is offline or busy**: commit and push, then end the turn with
  `wNNN: still open: queued for <the computer or kind of computer>`. The dispatcher queues it (`decide_work queue`
  with needs) and it starts when one fits.
- **Installers, daemon updates, reinstalls**: the ops worker (`ops_worker machine_update`) or ssh, never a person.
- **Before you call `waiting_on_person`**, read each question: if its only ask is a computer's availability or choice,
  it is a capacity wait, not a card. The portal refuses it (`shared/machineAsk.ts`), and the refusal costs you a turn.
