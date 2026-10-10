---
name: clean-up-after-yourself
description: "A worker removes what it made on disk before it reports a request done (builds, Captures, recordings, extra worktrees and clones, save copies, player slots, temp), and low disk on a machine is fixed by removing FF Factory's own leftovers or filing clean-up work, never by asking a person for a go. The same for Unity slots: its own -batchmode builds are gone before DONE, and a slot held by a stuck batch build is cleared with unity clear_batch, not waited out. Every delete is strictly inside the machine's worker install folder (root.json's root, $FF_WORKER_ROOT); outside it a worker only measures and reports sizes and lists what makes FF Factory write there, whatever the brief says (w896)."
date: 2026-10-07
---

# Clean up after yourself; low disk is never a person's question

**Rule.** Before you report a request done, remove what you made on disk for it: player builds,
Captures, recordings and screenshot sets (publish the proofs your report links first), worktrees
and clones you added, save copies you put in the shared saves folder, the player slots you filled,
and scratch outside your own temp folder. Say in the report what you removed and how much it freed.

When a machine is short of disk, FF Factory's own leftovers are not anyone's personal files, and
removing them needs nobody's go: player slots nobody holds, old agent worktrees whose work is
pushed, finished agents' `ffa-<session>` temp folders and build output of closed requests, all
**inside the machine's worker install folder** (`$FF_WORKER_ROOT`, w896: outside it you measure and
report and delete nothing, see [delete only inside the worker root](#delete-only-inside-the-workers-install-folder-outside-it-measure-and-report-w896);
Unity Hub's editor versions are outside it, so they are listed, not removed).
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
  empty, `git rev-list --count HEAD --not --remotes` = 0). Something you cannot attribute is listed, not removed.
  A Unity editor version nothing names is in Unity Hub's folder, outside the worker install folder: you measure it and
  report its size ([delete only inside the worker root](#delete-only-inside-the-workers-install-folder-outside-it-measure-and-report-w896), w896).
- Never delete another agent's work in progress or a protected path (the main clone, the daemon's
  folder): the harness blocks those anyway.
- Orchestrators and the dispatcher: low disk on a machine (a `[machine <id>] Clean-up cannot free
  enough disk space` notice, DISK in `list_machines`, a worker saying so) gets `machine_cleanup`
  and then clean-up work filed for that machine. Never a question to its owner.
- Since FF Factory PR #200 (w626) a machine's daemon also removes these leftovers by itself
  whenever its free space is below the soft threshold (FF Factory `docs/self-recovery.md`, "FF
  Factory's own leftovers"). That is the net under this rule, not a reason to skip it.

## Delete only inside the worker's install folder; outside it, measure and report (w896)

**Rule.** Before any delete, name the folder it is in and the machine's worker install folder (the `root` of its
`root.json`; `$FF_WORKER_ROOT` is set in your environment; your sandbox, your `$TMP`, the player slots and the nightly
lab are inside it). Inside: delete what you made or what FF Factory left, as the [clean up after yourself](#clean-up-after-yourself-low-disk-is-never-a-persons-question)
lesson says. Outside: **do not delete**. Measure (`du -sh`, `Get-ChildItem | Measure-Object -Sum Length`), report the
sizes, and list every setting, script or tool that makes FF Factory write there, so the write can be moved inside the
folder (a request of its own for the machine's owner). The one exception is a save copy you put in the game's saves
folder (`LocalLow\Never Games\finalfactory\saves\<your-copy>`), which you remove yourself.

This holds when the brief says otherwise. A clean-up brief that tells you to clear C:, AppData, the system temp, the Unity
Hub installer, dotnet or package caches, `LocalLow` test output or `~/.claude` transcripts is wrong: do the measuring,
say in the report that you did not delete there and why, and carry on with what is inside the folder. Do not ask a
person to approve the delete either; the answer is already "no, only inside the folder".

**Why.** 2026-10-10 (w896): w876, LothDesktop's low-disk clean-up, deleted on C: outside `D:\work\ffw` (dotnet workload
temp, the Unity Hub installer, Temp entries past three days, `LocalLow\Never Games\finalfactory` test output,
`~/.claude` transcripts past seven days; worker 37a50761's transcript). The dispatcher's own brief told it to, copying the
w626 rule ("remove FF Factory's own leftovers, never ask a person"), which had no boundary; w892 was then filed to clear
outside the folder too. Lothsahn: "Why are you clearing C: on LothDesktop?  How much space are the unity caches using?  In
general we should only be clearing D:", then "Sorry, in general we should only be clearing data in the install folder for
the worker".

**How to apply.**

- The [delete checklist](../checklists/delete.md) is the line that would have caught it: where is the root, is every
  path of this delete strictly inside it.
- Brief writers (the dispatcher, the orchestrators): never put a path outside the root in a delete; for what lies outside,
  ask for sizes and a list of what makes FF Factory write there. A "biggest remaining" list in a notice is for
  measuring, not an inventory to clear.
- FF Factory enforces the same rule where it can (w896): the daemon's own pass on a machine with a root removes only
  what is inside it and lists the rest (`fenceToRoot`, docs/self-recovery.md "Where clean-up may delete"), and the
  sandbox guard refuses an `rm`, `Remove-Item`, `del`, `rd`, `find -delete` or `xargs rm` outside the root
  (`server/rootFence.ts`). A refusal quotes the rule; it is not a prompt to find another way (a script, `shutil.rmtree`
  and a variable it cannot expand are the guard's known holes, and the rule binds you there too).
- A machine without a root install (the portal's own host, an old install) has no folder to name: say so and measure
  only, and an owner can name the folder for it.

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
