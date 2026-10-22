---
name: clean-up-after-yourself
description: "On Windows, disk work stays on the install drive, never C:, not even to measure (w1755). Workers do NOT clean up (w913): leave everything you make in your own $TMPDIR (clones, logs, builds, tour output, scratch); the daemon removes it a few minutes after no request waits for you any more (closed, or moved to another worker; a wait for CI or a person, a stop or a pause keeps it whole, since w1097) and your sandbox's build and capture output when it is released, so no rm, no player_slots prune and no clean-up step before DONE, and no rm mid-task to reuse a folder: each test leg writes to a new $TMPDIR/<leg>-<timestamp> (w1097). The one delete left to a worker (a huge build mid-task, disk short) is a plain rm -rf under $TMPDIR, which the session answers itself with no approval, and a save copy you put in the saves folder, named with your temp folder's name in front. Low disk on a machine is fixed by the harness or by filed clean-up work, never by asking a person. Every delete is strictly inside the machine's worker install folder (root.json's root, $FF_WORKER_ROOT); outside it a worker only measures and reports (w896). A clean-up deletes only the folders `ff-leftovers folders` marks DELETE (closed requests and orphans); the temp, build and review folders of a worker whose request is open, stalled or paused are kept whether or not its process runs (w1379), and a folder holding a git clone with uncommitted, unpushed or stashed work is kept whatever the ledger says: check its git state or the portal's clean-up log first (w1387). A -batchmode build you started is ended before DONE."
date: 2026-10-10
---

# Workers do not clean up; the harness does (w913)

**Rule.** Put everything you make for a request in your own temp folder (`$TMPDIR`, also TMP and TEMP:
`<install>/tmp/ffa-<session>`) and **leave it there**. Do not run `rm`, `Remove-Item`, `git worktree remove` or
`player_slots.py prune` to clean up, do not write a clean-up step before `DONE`, and do not list what you removed in the
report. Publish the proofs your report links (`publish_review`, `specs/<NNN>/proofs/`) before you end: the rest goes.

**Not mid-task either: a test leg gets a new folder, never a cleared one** (w1097, 2026-10-12). w1079's worker ran its tour
twice per screen size into `$TMPDIR/f1920` and `$TMPDIR/f1280` and, to rerun them, sent `rm -rf $TMPDIR/f1920
$TMPDIR/f1280` inside its long test command; Claude Code's dangerous-rm check stopped it for a person (its PR #1536: "the
evidence was re-run until both legs agreed"). lothsahn: "For w1097 why are workers deleting stuff in temp? Can't we have
the cleanup process when a worker is done do this for them so the worker doesn't have to worry about it?" It does: write
each leg to `$TMPDIR/<leg>-<timestamp>` (`OUT="$TMPDIR/f1920-$(date +%H%M%S)"`) and point the report at the newest; the old
ones go with the folder. Measured that day: the portal's clean-up log on lothdesktop lists whole finished sessions'
folders removed (`ffa-dd8193f8` 5.3 GB, `ffa-476c7481` 3.8 GB). It also showed the sweep was wrong about pauses: it
emptied the folders of b3327616 (w1097) and dcf976fc (w1086, its "before" clips and a player build in progress) while they
were only stopped for LothDesktop's V: grow. FF Factory now keeps a stopped worker's folder while a request still waits
for it (FF Factory PR #350, `server/resumable.ts`); on a machine whose daemon predates that, a long wait can still lose
scratch, so publish proofs as soon as you have them.

What removes it, and when (FF Factory `docs/self-recovery.md`, "Workers do not clean up"):

- your temp folder, a few minutes after no request waits for you any more (your requests closed, or moved to another
  worker; a wait for CI or a person, a stop or a pause keeps it whole, w1097): everything but git clones; the clones six hours
  after that, unless one holds work nothing else has (that one is kept and listed);
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

On Windows, outside the install folder's drive you do not even measure: [the install drive only](#windows-disk-work-stays-on-the-install-drive-never-c-w1755) (w1755).

**Rule.** Before any delete, name the folder it is in and the machine's worker install folder (the `root` of its
`root.json`; `$FF_WORKER_ROOT` is set in your environment; your sandbox, your `$TMP`, the player slots and the nightly
lab are inside it). Inside: delete what you made or what FF Factory left, as the [clean up after yourself](#clean-up-after-yourself-low-disk-is-never-a-persons-question)
lesson says. Outside: **do not delete**. On macOS and Linux, measure (`du -sh`), report the sizes, and list every
setting, script or tool that makes FF Factory write there, so the write can be moved inside the folder (a request of its
own for the machine's owner). On Windows, never look at C: or another drive at all, not even to measure
([the install drive only](#windows-disk-work-stays-on-the-install-drive-never-c-w1755), w1755). The one exception is a save copy you put in the game's saves
folder (`LocalLow\Never Games\finalfactory\saves\<your-copy>`), which you remove yourself.

This holds when the brief says otherwise. A clean-up brief that tells you to clear C:, AppData, the system temp, the Unity
Hub installer, dotnet or package caches, `LocalLow` test output or `~/.claude` transcripts is wrong: on macOS and Linux do
the measuring, on Windows not even that (w1755), say in the report that you did not delete there and why, and carry on
with what is inside the folder. Do not ask a
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

## Windows: disk work stays on the install drive, never C: (w1755)

**Rule.** On a Windows machine, every piece of disk work (a clean-up, a low-disk check, a leftover scan, a disk
measurement, "where did the space go") reads, measures and deletes only on the drive of the worker install folder:
the drive of `$FF_WORKER_ROOT` (the `root` of the machine's `root.json`), `V:` on LothDesktop (`V:\ffw`), `F:` on BEAST
(`F:\ffw`). Never C:, not even to measure: no `du`, `dir /s`, `Get-ChildItem -Recurse`, `find`, `tree`, `robocopy /L` or
`ff-leftovers check` of the home folder, `AppData`, `~/.claude`, the system temp, Unity Hub, package caches or the game's
`LocalLow` folder. Read the drive from the root, never assume a letter. If the install folder itself is on C:, look only
inside it and say so in your report.

A brief, a notice or an orchestrator's question that asks you to measure C: ("where did AppData's space go") is wrong:
measure inside the install folder, report what you freed and what is still short there, and say that you did not look
at C: and why. Do not ask a person to look there either. macOS and Linux keep the w896 rule: outside the install folder
you measure and report.

A save copy you put in the game's saves folder (under `LocalLow` on C:) for a test is a test step, not disk work: it stays
allowed (`read_rules saves`).

**Why.** 2026-10-22 (w1754): LothDesktop's clean-up worker ran `du` over `C:\Users\…\AppData` and `~\.claude` after the
orchestrator asked where AppData's space went. It deleted nothing on C:, but the w896 rule told it to "measure and report"
outside the install folder, the daemon's low-disk notice named the home folder and AppData as the biggest consumers, and
the w1561 lesson here sized "the whole home folder" with robocopy. Lothsahn: "Your worker on LothDesktop is still scanning
c:  it should not.  You need to only look at v:.  Stop messing with my c:", then "Fix the instructions for Windows boxes
to only look at v:".

**How to apply.**

- The [delete checklist](../checklists/delete.md) item 1a is the line that would have caught it: on Windows, is every path
  you are about to measure or delete on the install drive?
- Brief writers (the dispatcher, the orchestrators): a clean-up brief for a Windows machine never asks for a size, a scan
  or a question about C:.
- FF Factory enforces it where it can (ff-factory w1755, `docs/self-recovery.md` "Windows: the install drive only"): the
  sandbox guard refuses those scans of a path off the install drive (`checkOffDriveScan`, `server/rootFence.ts`), the
  delete fence's refusal says the drive rule, `ff-leftovers check` keeps such a path without looking at it, and the
  daemon neither measures nor lists anything off the install drive in its low-disk notice. A refusal quotes the rule; it
  is not a prompt to find another way (a script, python's `os.walk` and a variable it cannot expand are the guard's known
  holes, and the rule binds you there too).

## Measure Windows folders with robocopy /L, not Git Bash du (w1561)

**Rule.** Only on the install drive (w1755: never a folder on C:, [the install drive only](#windows-disk-work-stays-on-the-install-drive-never-c-w1755)).
On Windows, size a folder with `robocopy <dir> <a path that does not exist> /L /S /E /BYTES /NFL /NDL /NJH /NC
/NP /R:0 /W:0 /XJ /MT:16` and read its `Bytes :` line, one call per child folder. `/L` only lists and copies nothing, and
`/XJ` skips junctions so nothing is counted twice. Never run Git Bash `du` on a large tree. When free space looks
unchanged after a delete, re-read it exactly with `Get-PSDrive` of the install drive (`Get-PSDrive V` on LothDesktop).

**Why.** 2026-10-19, lothdesktop (w1561, disk clean-up): Git Bash `du -m --max-depth=1` took 19 minutes on
`AppData\Local` (69 GB) and was still in `AppData\LocalLow` when it was stopped. The robocopy script measured `.cache`
and `AppData\Local\Unity` in 0.6 s and the whole home folder (180 GB, 17 roots) in a few minutes. Git Bash `df -h`
still showed 78G free on V: after a 10 GB delete, while `Get-PSDrive` showed 81.40 GB.

**How to apply.** Write the loop as a `.ps1` in `$TMPDIR` that takes a list of roots on the install drive (the install
folder's children) and prints the biggest children in GB, then run it once for every root you need. The home folder and
`AppData` measured in w1561 are on C:, which w1755 put off limits: the guard refuses `robocopy /L` there now.

## A clean-up never takes the folders of a request that has not closed (w1379)

**Rule.** Before you delete a folder that is not yours (another worker's `tmp/ffa-<session>`, a `scratch/` or review folder named for a
request, a sandbox's `Builds/` or `.nightly-builds/` output), run `ff-leftovers folders` (the whole list) or `ff-leftovers check <path>...` (the
paths you mean to delete; exit 1 means keep) and delete **only what it marks DELETE**. It judges the ledger's facts, which you cannot read
yourself: a folder is deletable only when its request is closed (done, merged, rejected, cancelled) or it belongs to no worker at all (an
orphan). The temp, build and review folders of a worker whose request is **open, stalled or paused** are KEEP rows **whether or not the worker's process runs**:
a usage limit, a wait for CI, a wait for a person's OK or a hold stops the process and not the request. A KEEP row you report with its reason
("skipped: w1332 stalled, a735f37c resumes"); you do not weigh it against the space you need. When the command answers "no ledger facts", "not
connected", "predates w1379" or is not found (an older daemon), **delete no worker's folder at all**, say so in the report, and let your orchestrator get
the daemon updated; the space you can still free is your own sandbox and what is clearly FF Factory's own and inside the install folder.

**Never take a list of live or "will resume" workers from a brief and delete the rest.** A brief's list is a guess of the dispatcher at
the minute it wrote it; the ledger moves (a request stalls on a usage limit, a person asks for a change, a hold ends). Brief writers (the
dispatcher, the orchestrators): a clean-up brief says "run `ff-leftovers folders` and delete only its DELETE rows", never "these workers are live".

**Why.** 2026-10-15 (w1379): w1374, LothDesktop's low-disk clean-up (worker d314b54b, V:\ffw), deleted the temp folder of stopped worker
a735f37c, which is on w1332 (the comet catch-tail VFX). The ledger had stalled w1332 at 13:15 on a usage limit (revived at 13:59) and it was then
waiting for Ben's OK of the look; it lost its player builds and preview clips and rebuilt them (the look itself was committed). The brief
listed five live workers and "39b00201 and d4c4ff2c are stopped but will resume", and a735f37c was on neither list. The daemon's own sweeps
keep such a session (FF Factory `server/resumable.ts`, w1097); the by-hand delete had no ledger behind it. A worker can read only its own
requests (`read_work`), so the machine now tells it: FF Factory PR #402 (`server/cleanupFolders.ts`, `ff-leftovers folders|check`).

**How to apply.**

- The [delete checklist](../checklists/delete.md) item 2a is the line that would have caught it: whose folder is it, and what does the ledger say about its request.
- Not provable means KEEP: old facts (the daemon writes them every 30 s), a daemon not connected to the portal, a folder naming no request,
  a path outside the install folder (w896). The command says why in its answer.
- The daemon's own passes follow the same rule, and wait for the portal's welcome before they judge any worker folder (FF Factory
  `docs/self-recovery.md`, "A clean-up worker's deletes are judged by the ledger").
- The portal host's review folder (`/srv/fff/review/<topic>`) is outside any worker root, so no sweep takes it and `ff-leftovers` cannot judge
  it: a topic named for a request that is not closed is not yours to delete either.

## A DELETE row is not a go for a folder that holds a git clone with work (w1387)

**Rule.** Before you delete any folder that holds a git clone or worktree (another worker's `tmp/ffa-<session>/<clone>`, a `wt-*`
worktree, anything with a `.git` in it or a few levels below), even on a DELETE row of `ff-leftovers folders`, look at its git state or at what
the portal's own clean-up said about it, and keep it if either says it holds work:

```sh
git -C <clone> status --porcelain              # uncommitted or untracked files
git -C <clone> log --oneline --branches --not --remotes   # commits no remote has
git -C <clone> stash list                      # work set aside
```

or `portal_logs` with `source: cleanup`, `machine: <id>`, `grep: <folder name>`: a line "kept for a person: ... holds a git repo with
uncommitted or unpushed work" means the sweeps keep it on purpose, and so do you. Report it as KEEP with that reason; it is not
yours to judge whether the work matters.

**Why.** 2026-10-15 (w1387): w1385, LothDesktop's next low-disk clean-up (worker d18033fb), deleted `V:fw	mpfa-31ffe8cc` (538 MB, the
clone `ff` of the nightly merge review w1367) and `V:fw	mpfa-28ebd585` (45 MB, the worktree `wt-w1258-claims-gather-parallel`) on DELETE
rows: their requests were done, and `ff-leftovers` judged by the ledger alone. The portal's clean-up log had kept both "for a person:
holds a git repo with uncommitted or unpushed work" (31ffe8cc at 21:11Z, 21:32Z and 22:11Z; 28ebd585 at every pass since 2026-10-14
05:40Z). The uncommitted files went with them. FF Factory PR #405 (w1387) makes `ff-leftovers folders|check` run the sweeps' own git check, so a
daemon updated after it shows these as KEEP; until a machine's daemon is, this check is yours.

**How to apply.** The [delete checklist](../checklists/delete.md) item 2b is the line that would have caught it.

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

## Processes you started end before DONE (w1196, w1197)

### Not `ff-leftovers end` before the w1222 fix

**Do not run `ff-leftovers end` until FF Factory's w1222 fix is on your machine**: it is there once
`grep -c FF_LEFTOVERS_CALLERS "$(command -v ff-leftovers)"` prints 1 or more. On 2026-10-13 four workers on Windows (w1203, w1215, w1216, w1219) ran
`ff-leftovers end` and their own Claude process died at once with exit code 1: Git Bash's fork+exec broke the
parent chain the command walks, so it took claude.exe, its shell and its MCP server for leftovers and ended them.
Until the fix is there, run `ff-leftovers list` only (it reads, it ends nothing), end a player or job it lists by its
pid yourself (`kill <pid>`; never claude, bash, sh, node, conhost, uv, uvx or an MCP server's python), say in the
report what you ended, and leave the rest to the daemon, which ends what your session started 2 min after your
process stops. Wherever this skill set says `ff-leftovers end`, read this first.

**Rule.** Files you leave; processes you end. Before you report DONE, and before you end a turn that leaves no
`wake_me` check-in for a run still going, run `ff-leftovers list`, then `ff-leftovers end`, and say in the report
what it ended or that nothing was left. It ends what your own session started that still runs (by the
`FF_SESSION_ID` every process you start inherits): game players, Xvfb and its window manager, ffmpeg, background
jobs and scripts, batch builds, servers. It never ends your own shell chain, claude's MCP servers, an interactive
editor or another worker's processes. Give every player you start a way to end by itself: `-ffSoloQuitAfterSeconds
<n>`, or `timeout -s TERM <n>` around its launch. A run you need while you are stopped needs a check-in set for when
you will look at it.

**Why.** 2026-10-13, biscuit: Ben's fans ran at 100% around the clock. Two headless players that workers had started,
pid 2459040 (slot1-1, Xvfb :101, worker a33e1437, w1072) and pid 2311211 (slot2-0, Xvfb :62, worker 1290a5e0,
w1025), were still up 27 h and 34 h after those workers stopped and their requests closed, about 6 cores between
them, beside 17 Xvfb displays of earlier workers and a 38-hour-old dbus/gvfs session of a third. Nothing reaped them
and no report had said they were still running. Ben (w1197): "please update the fff harness to ensure everything is
properly cleaned up so we arent wasting system resources on our machines after work is done".

**How to apply.**

- FF Factory's daemon ends the rest by itself (ff-factory `machine/leftovers.ts`, docs/self-recovery.md): everything
  a session started, 2 min after its process stops once no request waits for it, 10 min after it stops while one still
  does, and never before a pending check-in is due plus 10 min; a game player nobody owns 10 min after it is first
  seen so. That is a safety net, not the teardown: the report still says what you ended.
- `ff-leftovers` comes with the FF Factory daemon (w1196). On a machine whose daemon predates it (the command is not
  found), end your own players by pid: `player_slots.py status` lists the leases, and `kill <pid>` of a player passes
  the hook (it refuses a kill whose command names Unity, node, claude or PowerShell).
- A player paused in its Esc menu or back at the title cannot be closed through the agent channel
  ([project-memory `visual-check-players-must-quit-themselves`](../../project-memory/memories/visual-check-players-must-quit-themselves.md)):
  the quit timer or `ff-leftovers end` does it.
- **A stopped background shell leaves its children running, and `ff-leftovers list` may not show them** (w1561,
  2026-10-19, lothdesktop). After `TaskStop` on a background Bash job running `du`, `du.exe` (pid 19908) kept running,
  and `ff-leftovers list` printed "Nothing your session (…) started is still running". Before DONE, also look for your
  own tool processes (`tasklist /FI "IMAGENAME eq du.exe"`) and read each command line (`Get-CimInstance
  Win32_Process -Filter "ProcessId=<pid>"`). End one by pid only when its command line shows it is yours.

## A runaway task output, and `python -` through `eval` (w876, w899)

**Rule.** Do not run `python - <<'E' ... E` inside `eval '...'`, `bash -c "..."` or any wrapper that re-parses
the command: write the script to a file in your temp folder and run `python file.py`. A background process of yours is
ended before DONE; the daemon also ends the writer of an oversize task `.output` file once your session has stopped (w899),
but a live one is only listed, so a process of yours that loops is yours to end.

**Why.** 2026-10-10: a worker's `eval 'python - <<E ... E'` lost its heredoc, so `python -` opened its interactive
REPL and looped on `OSError: [WinError 123]` for a day, writing a 99.6 GB Claude task `.output` file; LothDesktop's D:
fell from 104 GB to 60 GB free. Deleting the file freed nothing until the process (PID 23756) was ended. The
daemon's clean-up now removes such a file and ends its writer once the session has stopped (FF Factory PR #284, w899).

## Keep rm out of long commands (w63, w194, w1097)

(Merged here from its own lesson file, w1453, to keep the lessons under their cap.)

**Rule.** Never chain `rm` into a command that then does real work or waits. Delete in a short
command of its own, or don't delete: write to a new, uniquely named folder and overwrite files
in place.

**Why.** Late September and early October 2026, in FF Factory sandboxes. Claude Code can ask for
permission on a destructive shell command (a delete with a wildcard, `-rf`, a path outside the
working folder), and the whole compound command waits with it. Nobody watches a worker's
terminal, so it waits until a person happens to open the sandbox panel. Ben's orchestrator
reported several workers stuck this way for 15 to 90 minutes. The "waiting for permission"
notices in the orchestrators' transcripts show the shape each time, a clean-up glued to the real
work:

- `cd ... && cp ... && rm -f clips/*; ... python take.py ...` (w63, clip recording)
- `L=.../look && rm -f $L/*.jpg && ... python strip.py ...` (w194, frame strips)
- `... && rm -f $N/*.txt && for pair in ...` (w165, proof numbers)
- a wait loop that ended in `[ -f $D/done.txt ] && rm -f $D/*.txt && ...`
- `du -sh ...; rm -rf slot-5/Builds/w157-fix ...` (w157, build clean-up)

**How to apply.**

- Make the output folder new each run (`out/run-$(date +%H%M%S)`), so there is nothing to clear.
- Let tools overwrite: `ffmpeg -y`, a file opened for writing. That needs no delete.
- When a delete is needed, run it alone and first. If it prompts, you learn in seconds, and
  nothing else is held up behind it.
- Scratch in your temp folder needs no clean-up for the run to continue; the harness removes it
  after the session (w913: workers do not clean up). A delete under `$TMPDIR` that is needed mid-task gets no prompt.
- If a command has not returned and you cannot tell why, a prompt is one of the likelier causes.
  Say in your report that you may be waiting on one.

### What asks, measured (w1097, 2026-10-12)

 lothsahn: "I just got prompted to accept a bash prompt in w1079. Why did it
do that, and how do we allow it to do what it just needed to do without a complex bash prompt?" w1079's worker had sent one
multi-line command: a `rm -rf` of its last run's folders in `$TMPDIR`, a shell function with a `cp` retry loop restoring
the game's `settings.json`, its test-leg script, a grep of the result. Claude Code 2.1.284 was driven through a stand-in
Messages API with the exact commands (FF Factory `docs/self-recovery.md`, "Routine test steps without a prompt"): in
bypass mode, where workers run, a function, a loop, several lines, `&&`, a pipe, a heredoc, `$(...)`, a `cp` into
`LocalLow`, `bash "$TMPDIR/leg.sh"` and `python scripts/game_data.py ...` never ask. Only its dangerous-rm check does:
`rm -rf $TMPDIR/{a,b}`, `rm -f $TMPDIR/*.log` (a `$VAR` with a glob or a brace list), `rm -rf /x` or `C:/x` (a critical
path). Plain `rm -rf "$TMPDIR/f1920"` does not. FF Factory now answers such a prompt itself when every delete in the
command is written out under `$TMPDIR` (after the portal deploy that carries w1097), but the routes below never ask at all:

- Give each leg a new folder, `$TMPDIR/<leg>-<timestamp>` (`OUT="$TMPDIR/f1920-$(date +%H%M%S)"`), never a cleared
  one: the daemon removes your whole temp folder when the session ends (w913). Nothing to delete.
- Put multi-step test logic in a script file in `$TMPDIR`, written with the Write tool, and run `bash "$TMPDIR/leg.sh" 1920`.
- Back up and restore the game's settings and saves with the game repo's `python scripts/game_data.py`
  (`snapshot`, `restore`, `run --name <leg> -- <command>`, `get <key> --name <leg> --after`), not a `cp` loop into
  `LocalLow`. It writes only `UserData/settings/settings.json`, `LocalSettings/settings.json` and the saves you name.
- The w913 rule above already said "do not clean up"; w1079's worker did not count a rerun's output folders as clean-up.
  They are: never delete a folder to use it again.

## A listener binds 127.0.0.1 or runs from a stable path, never from $TMPDIR (w1742)

**Rule.** Windows Firewall shows an "allow access" prompt the first time a program path listens on any address but
loopback: 0.0.0.0, `::`, or no host at all, which is the default for node's `listen(port)` and Python's
`bind(("", port))`. A listen on 127.0.0.1 never prompts, and neither does a path a rule names. The prompt sits over the
unattended desktop and over every clip taken under it. So:

- Bind what you start to 127.0.0.1: a test server, a mock, a probe, a dev server (`--host 127.0.0.1`). A port check
  binds loopback and finds a wildcard holder another way: connect to it, or on Windows read `netstat` (game repo
  `player_slots.udp_port_free`). On Windows a loopback bind succeeds beside a socket on 0.0.0.0 of the same port
  (measured).
- Never unpack a runtime into `$TMPDIR` and run it: every session's temp folder is a new path, so a new prompt. On a
  Windows worker, node 24 is on PATH from the root's `tools\node` (ff-factory `server/agentNode.ts`). If it is missing
  or too old, say so in the report; do not download one.
- A built player runs only from its slot. A launch that warns `no inbound firewall rule names ...`, or a prompt over a
  slot player, means that machine's install lacks the rule. Put `python scripts/nightly/player_slots.py firewall`'s
  output in the report, and have the orchestrator send the ops worker for an elevated rerun of the install. Never ask a
  person to click the prompt.

**Why.** lothsahn, 2026-10-22: "We made a bunch of static slots to fix the windows firewall which has solved it there,
but now we're making random folders under the temp directory and nodejs is triggering the windows firewall." Measured
on lothdesktop:

- The firewall log (events 2097) held rules from prompts for three `V:\ffw\tmp\ffa-*\` node.exe copies (2026-10-12 to
  10-20). Each was a worker that downloaded node 24 into its temp folder to run ff-factory's tests; the machine's node
  is 22.17.
- A listen spy over that suite found `server/testPorts.ts` binding 0.0.0.0 41 times, and nothing else beyond loopback.
  ff-factory's `server/listenLoopback.test.ts` now fails a wide listen.
- On BEAST the same day, a slot2-0 prompt covered all 12 of w1722's clips. On lothdesktop a slot player listened on
  0.0.0.0:55000 with no prompt, because its rule exists. Checking what a process holds:
  `Get-NetTCPConnection -State Listen -OwningProcess <pid>` and `Get-NetUDPEndpoint`.
