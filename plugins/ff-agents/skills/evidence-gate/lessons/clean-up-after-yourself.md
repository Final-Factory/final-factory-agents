---
name: clean-up-after-yourself
description: "A worker removes what it made on disk before it reports a request done (builds, Captures, recordings, extra worktrees and clones, save copies, player slots, temp), and low disk on a machine is fixed by removing FF Factory's own leftovers or filing clean-up work, never by asking a person for a go. The same for Unity slots: its own -batchmode builds are gone before DONE, and a slot held by a stuck batch build is cleared with unity clear_batch, not waited out."
date: 2026-10-07
---

# Clean up after yourself; low disk is never a person's question

**Rule.** Before you report a request done, remove what you made on disk for it: player builds,
Captures, recordings and screenshot sets (publish the proofs your report links first), worktrees
and clones you added, save copies you put in the shared saves folder, the player slots you filled,
and scratch outside your own temp folder. Say in the report what you removed and how much it freed.

When a machine is short of disk, FF Factory's own leftovers are not anyone's personal files, and
removing them needs nobody's go: player slots nobody holds, old agent worktrees whose work is
pushed, finished agents' `ffa-<session>` temp folders, build output of closed requests, and Unity
editor versions no sandbox's or the main clone's `ProjectVersion.txt` names and nothing runs.
Remove them yourself (or run `machine_cleanup` when you are an orchestrator), and report what went.
A person decides only about their own files: documents, downloads, their own projects and saves,
and a worktree with unpushed work. List those in your report with sizes; do not ask about the rest.

**Why.** 2026-10-07 (w596, w626): the m3 drifted under its 50 GB disk guard. A worker on it found
about 78 GB of FF Factory's own leftovers (old player slots in `~/nevergames/ff-players`, an old
agent worktree, Unity editors no project used) and asked for a person's go instead of removing
them. The orchestrators passed the question to Ben and Lothsahn. Ben: "no YOU free up disk space,
like you are instructed to in this harness. stop making us tell you to do it. PLEASE FOR THE LOVE
OF GOD CLEAN UP AFTER YOURSELF". The leftovers were there in the first place because earlier
workers left their slots, worktrees and installs behind when they finished.

**How to apply.**

- Run the clean-up step of the [done checklist](../checklists/done.md) before every `DONE: wNNN`
  ([say DONE per request](say-done-per-request.md)).
- Before removing, check that the thing is FF Factory's and finished: a player slot with no live
  lease (`python scripts/nightly/player_slots.py status`, then `prune` empties every slot nobody
  holds), a worktree with nothing uncommitted, untracked or unpushed (`git status --porcelain`
  empty, `git rev-list --count HEAD --not --remotes` = 0), a Unity version no `ProjectVersion.txt`
  names and no process runs from. Something you cannot attribute is listed, not removed.
- Never delete another agent's work in progress or a protected path (the main clone, the daemon's
  folder): the harness blocks those anyway.
- Orchestrators and the dispatcher: low disk on a machine (a `[machine <id>] Clean-up cannot free
  enough disk space` notice, DISK in `list_machines`, a worker saying so) gets `machine_cleanup`
  and then clean-up work filed for that machine. Never a question to its owner.
- Since FF Factory PR #200 (w626) a machine's daemon also removes these leftovers by itself
  whenever its free space is below the soft threshold (FF Factory `docs/self-recovery.md`, "FF
  Factory's own leftovers"). That is the net under this rule, not a reason to skip it.

## Unity batch builds and the slots they hold (w791)

**Rule.** A `-batchmode` Unity build you start runs under `unity-slot run` (the game repo's build scripts
already do) with a `-logFile`, and is gone before DONE: `unity-slot status` shows none of yours. When
`mcp__machine__unity` refuses a start because a batch build holds the slot for more than an hour, call it with
`action: "clear_batch"`: the daemon's reaper (`machine/unityReaper.ts` in FF Factory) ends the sandboxes' batch
builds whose owner is gone (10 min without log or CPU progress, or 90 min old) or that hang with a live owner
(an hour old, 30 min without progress), removes the stale `Temp/UnityLockfile`, and says for every build it keeps
why. A build it calls healthy is waited on with `wake_me`; the limits do not move on request. Nobody ends Unity by
hand (the hook refuses it) and no person is asked to approve it.

**Why.** 2026-10-09 (w791): twice a batch build held a sandbox's Unity slot for hours until a person approved
ending it through the ops worker. LothDesktop pid 3856, a nightly prepare build of slot4, hung 209 min on "More
than one copy of bee_backend running in slot4" with its script alive and blocked w769's worker (the Steam Deck
hint draw-order fix); m5 pid 81390, a worker's Mac build, was 15 h old with parent pid 1. Ben's rule: the harness
learns from a repeated problem.

**How to apply.**

- Measured on 15 healthy nightly builds (4.5 to 36.9 min, median 8.4): a build under an hour old is not stuck.
- An answer of "protocol 8 ... cannot clear" means the daemon is old: say so in the report; the orchestrator asks
  for the deploy.
- Do not start a batch build in a sandbox whose interactive editor runs (two copies of bee_backend lock each
  other); `unity stop` first.
- FF Factory side: `docs/unity-lifecycle.md`, "Orphaned and hung batch builds are ended".
