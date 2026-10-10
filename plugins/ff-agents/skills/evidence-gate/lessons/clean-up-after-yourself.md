---
name: clean-up-after-yourself
description: "Workers do NOT clean up (w913): leave everything you make in your own $TMPDIR (clones, logs, builds, tour output, scratch); the daemon removes it a few minutes after your process ends and your sandbox's build and capture output when it is released, so no rm, no player_slots prune and no clean-up step before DONE. The one delete left to a worker (a huge build mid-task, disk short) is a plain rm -rf under $TMPDIR, which the session answers itself with no approval, and a save copy you put in the saves folder, named with your temp folder's name in front. Low disk on a machine is fixed by the harness or by filed clean-up work, never by asking a person. Every delete is strictly inside the machine's worker install folder (root.json's root, $FF_WORKER_ROOT); outside it a worker only measures and reports (w896). A -batchmode build you started is ended before DONE."
date: 2026-10-10
---

# Workers do not clean up; the harness does (w913)

**Rule.** Put everything you make for a request in your own temp folder (`$TMPDIR`, also TMP and TEMP:
`<install>/tmp/ffa-<session>`) and **leave it there**. Do not run `rm`, `Remove-Item`, `git worktree remove` or
`player_slots.py prune` to clean up, do not write a clean-up step before `DONE`, and do not list what you removed in the
report. Publish the proofs your report links (`publish_review`, `specs/<NNN>/proofs/`) before you end: the rest goes.

What removes it, and when (FF Factory `docs/self-recovery.md`, "Workers do not clean up"):

- your temp folder, a few minutes after your process ends (a request closed, a wait for CI or a person, a stop): everything
  but git clones; the clones six hours after, unless one holds work nothing else has (that one is kept and listed);
- your sandbox's cached builds beyond the newest, benchmark builds and capture output, when the sandbox is released;
- old nightly output, per-commit builds, stale scratch and runaway task output in the daily pass; player slots nobody holds
  and pushed agent worktrees when the disk is low.

Because the sweep waits for a process that names your folder, a build you leave running in it is not pulled from under it;
and because a clone with unpushed work is kept, push before you leave.

**The one delete left to a worker.** The disk is short in the middle of your task (a huge player build): free it with a plain
`rm -rf "$TMPDIR/<name>"` (PowerShell: `Remove-Item -Recurse -Force $env:TEMP\<name>`) with every path written out under
`$TMPDIR`. The session answers that itself, with no approval (`server/tempDelete.ts`); anything else asks a person, so do
not send it: the folder itself, `/tmp` (Git Bash's `/tmp` is not your folder), `..`, `~`, a variable that is not `$TMPDIR`, a
pipe, a redirect into a file, `$(...)`, a path outside the folder. A save copy you put in the game's saves folder (outside
the install folder, so no sweep takes it) is named with your temp folder's name in front, `ffa-<session>-<name>.zip`, and
`rm -f` on exactly that file is approval-free too; a save with another name is a person's. Never ask a person to approve a
clean-up: if a delete would ask, you do not need it.

When a machine is short of disk, FF Factory's own leftovers are not anyone's personal files and removing them needs nobody's
go: the daemon does it, or the orchestrators file clean-up work (`machine_cleanup`). That is for a clean-up request; an
ordinary worker leaves them. A person decides only about their own files (documents, downloads, their own projects and saves,
a worktree with unpushed work): list those with sizes, do not ask about the rest.

**Why.** 2026-10-10 (w913, lothsahn): "Random clean up commands take a lot of approvals. Is there some way we can build what
those cleanup commands are doing into the harness (like we have for trimming the Burst Cache) so that they run every time a
worker is done, and stop asking the workers to do cleanup and need approvals?" Claude Code asks about `rm -rf`, a wildcard or
a path outside the working folder, so `rm -rf $TMPDIR/ff-factory $TMPDIR/ffbox $TMPDIR/*.log` (w901) and `rm -rf $TMPDIR/ff
$TMPDIR/*.txt` (w907, approved twice by Ben) waited for a person. Measured on beast over 8 days: 1351 delete statements, 388 on
`$TMPDIR` or `/tmp` (100 sessions), 61 save copies, 57 `player_slots.py prune`, and 21 GB of `ffa-*` folders on disk anyway.
This reverses the instruction Ben's 2026-10-07 correction (w596/w626: "PLEASE FOR THE LOVE OF GOD CLEAN UP AFTER YOURSELF")
produced; the aim was a disk that stays free without him asking, which the daemon now delivers without the prompts.

**How to apply.**

- Builds, recordings, tour output and test saves go under `$TMPDIR`, not the worktree, `/tmp` or a shared scratch folder
  (the sweep and the guard know your folder; a build left in a sandbox's `Builds/` is taken at release only when it is a
  cached build beyond the newest or a bench or capture folder).
- Before you end: everything the report links is published; every clone you need is pushed.
- Never delete another agent's work in progress or a protected path (the main clone, the daemon's folder): the harness blocks
  those anyway.
- Orchestrators and the dispatcher: low disk on a machine (a `[machine <id>] Clean-up cannot free enough disk space` notice,
  DISK in `list_machines`, a worker saying so) gets `machine_cleanup` and then clean-up work filed for that machine. Never a
  question to its owner.

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

## A runaway task output, and `python -` through `eval` (w876, w899)

**Rule.** Do not run `python - <<'E' ... E` inside `eval '...'`, `bash -c "..."` or any wrapper that re-parses
the command: write the script to a file in your temp folder and run `python file.py`. A background process of yours is
ended before DONE; the daemon also ends the writer of an oversize task `.output` file once your session has stopped (w899),
but a live one is only listed, so a process of yours that loops is yours to end.

**Why.** 2026-10-10: a worker's `eval 'python - <<E ... E'` lost its heredoc, so `python -` opened its interactive
REPL and looped on `OSError: [WinError 123]` for a day, writing a 99.6 GB Claude task `.output` file; LothDesktop's D:
fell from 104 GB to 60 GB free. Deleting the file freed nothing until the process (PID 23756) was ended. The
daemon's clean-up now removes such a file and ends its writer once the session has stopped (FF Factory PR #284, w899).
