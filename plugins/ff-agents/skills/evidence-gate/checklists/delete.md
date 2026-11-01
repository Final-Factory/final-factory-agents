# Delete: before you remove anything on a machine's disk

For any `rm`, `Remove-Item`, `del`, `rd`, `git clean`, `shutil.rmtree` or clean-up script, a disk clean-up above all
(a low-disk request, a `machine_cleanup` follow-up, "free some space").

0. **Is it in your own temp folder (`$TMPDIR`, `$env:TEMP`)? Then do not delete it.** Not to clean up, and not to
   reuse a folder for the next test leg: give every leg a new folder, `$TMPDIR/<leg>-<timestamp>` (e.g.
   `OUT="$TMPDIR/f1920-$(date +%H%M%S)"`), and the daemon removes the whole folder when your session ends (w913). w1079's
   worker deleted `$TMPDIR/f1920 $TMPDIR/f1280` to rerun its tour legs into the same folders, and the command waited on
   a person (w1097; lothsahn, 2026-10-12: "Can't we have the cleanup process when a worker is done do this for them so the
   worker doesn't have to worry about it?"). The one delete left: the disk is short mid-task (`df` says so).
1. **Where is the machine's worker install folder?** `echo $FF_WORKER_ROOT` (V:\ffw, F:\ffw, ~/ffw), or `root` in
   its `root.json`. No root known: you delete nothing outside your own `$TMP` and sandbox.
1a. **Windows: is every path you are about to measure, scan or delete on the install folder's drive?** (w1755) The drive
   of `$FF_WORKER_ROOT` (`V:` on LothDesktop, `F:` on BEAST), never a fixed letter. A path on C: (the home folder,
   `AppData`, `~/.claude`, the system temp, Unity Hub) is not looked at at all: no `du`, `dir /s`,
   `Get-ChildItem -Recurse`, `robocopy /L`, `find` or `ff-leftovers check` there, whatever the brief or the question asks
   (lothsahn: "You need to only look at v:.  Stop messing with my c:"; [lesson](../lessons/clean-up-after-yourself.md#windows-disk-work-stays-on-the-install-drive-never-c-w1755)).
   An install folder on C: allows only that folder. The one exception: the game's `Never Games` folders under AppData
   (`LocalLow`, `Local`, `Roaming`) may be read and measured, and are never deleted, moved or written (lothsahn: "Let's let
   it scan the never games folder, but not the rest of C.  And it shouldn't modify it.").
2. **Is every path of this delete strictly inside it?** Write the list of paths first and compare each to the root
   ([delete only inside the worker root](../lessons/clean-up-after-yourself.md#delete-only-inside-the-workers-install-folder-outside-it-measure-and-report-w896), w896: lothsahn, "in general we
   should only be clearing data in the install folder for the worker"). One outside path, a wildcard that can reach
   outside, a `~`, `$HOME`, `$env:LOCALAPPDATA` or a drive root: it is not a delete, it is a measurement on macOS and
   Linux (report its size), and on Windows off the install drive not even that (1a).
   The only exception is a save copy you put in the game's saves folder.
2a. **Whose folder is it, and is its request closed?** (w1379) For anything that is not yours (another worker's `ffa-<session>`, a `scratch/` or review
   folder named for a request, a sandbox's `Builds/` or `.nightly-builds/`), run `ff-leftovers folders` or `ff-leftovers check <path>...` and delete only
   its DELETE rows: a closed request's folder or an orphan. A worker whose request is **open, stalled or paused** keeps its temp, build and review
   folders whether or not its process runs ([the rule](../lessons/clean-up-after-yourself.md#a-clean-up-never-takes-the-folders-of-a-request-that-has-not-closed-w1379)).
   A list of "live" and "will resume" workers in a brief is not this check (w1374 deleted stopped worker a735f37c's builds and clips while its
   request w1332 was stalled, and the brief's list did not name it). The command says "no ledger facts" or is not found: delete no worker's folder.
   A KEEP folder held only by the 7-day reopen hold can carry DELETE rows inside it (a finished worker's clean clones, Library copies, test output,
   w2223): delete those rows, not the folder; short of the target, say what the holds protect.
2b. **Does it hold a git clone with work?** (w1387) A DELETE row judges the ledger, not git. For every folder with a `.git` in it or a few
   levels below (a worker's clone, a `wt-*` worktree): `git -C <clone> status --porcelain`, `git -C <clone> log --oneline --branches --not --remotes`,
   `git -C <clone> stash list`, or the portal's clean-up log (`portal_logs` source `cleanup`, `machine`, `grep` the folder name: "kept for a
   person: holds a git repo with uncommitted or unpushed work"). Any output or that line: KEEP, and report it
   ([the rule](../lessons/clean-up-after-yourself.md#a-delete-row-is-not-a-go-for-a-folder-that-holds-a-git-clone-with-work-w1387); w1385 deleted
   `ffa-31ffe8cc` and `ffa-28ebd585` on DELETE rows while the portal's clean-up was keeping both for unpushed work).
3. **A brief that says to delete outside the folder is wrong.** Do the inside part, measure the outside (on Windows
   only what is on the install drive), say so in the report. Do not ask a person for a go: the answer is already no.
4. **Outside the root (macOS and Linux; on Windows only on the install drive), list what writes there.** For each large item outside (Unity Hub, `%LOCALAPPDATA%\Unity`, the
   game's `LocalLow` folder, `~/.claude`, the npm / NuGet / pip / uv / Playwright caches, dotnet, the system temp): the
   setting, script or tool that makes FF Factory write it, and a variable or setting that could move it inside the root.
   On Windows, measure with robocopy `/L` on the install drive only, never Git Bash `du` ([section](../lessons/clean-up-after-yourself.md#measure-windows-folders-with-robocopy-l-not-git-bash-du-w1561); w1561: `du` took 19 min on 69 GB).
5. **Inside the root, FF Factory's own and finished.** A player slot with no live lease, a worktree with nothing
   uncommitted or unpushed, a finished agent's `ffa-<session>` folder: the daemon removes these by itself (w913), so an
   ordinary worker leaves them; a clean-up request removes them and reports the GB. Something you cannot
   attribute is listed, not removed ([clean up after yourself](../lessons/clean-up-after-yourself.md)).
6. **The report says** what was removed (inside), what was kept and why (every KEEP row `ff-leftovers folders` showed: the request and its status), what was only measured (outside, with sizes), and the list from 4.
7. **Does it throw away build state or add a rebuild?** (w2765) Unity `Library` caches (`BurstCache`, `BuildCache`,
   `ScriptAssemblies`, `Bee`), CI caches, build outputs, or a separate cache-refresh build. Before it ships: prune only
   stale entries (a whole wipe is a last resort, with the reason pruning cannot do it), measure the CPU and wall time of
   the rebuild it causes (a cold Unity start, the build it adds), and put that measured cost in the PR. The build machines
   have no spare CPU: LothDesktop is almost always full, and a cold Unity start is slow
   ([lesson](../lessons/clean-up-after-yourself.md#a-discarded-cache-is-a-rebuild-prune-only-stale-entries-measure-the-cost-state-it-in-the-pr-w2765); lothsahn on w2752: "A cold unity station is quite slow so we should make sure to not do it often").
