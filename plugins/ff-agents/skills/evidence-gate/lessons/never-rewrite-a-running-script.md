---
name: never-rewrite-a-running-script
description: "Never overwrite or edit in place a shell script that a background run is still executing: bash reads a script as it goes, so the running process runs the new file's bytes from its old offset. Write each new version to a new file name. After stopping a background script, check ff-leftovers list for its orphaned children and git log for commits it made, before the next push (w3826)."
date: 2026-11-09
---

# Never rewrite a running script; after stopping one, look for what it left (w3826)

**Rule.** A shell script started in the background (`run_in_background`, `nohup`, a build or A/B driver) is read by bash
**a little at a time while it runs**. Overwriting it with Write or editing it in place makes the running process carry on
from its old byte offset in the *new* file and run lines it was never meant to run. So:

1. Write each new version of a script to a **new file name** (`build2.sh`, then `build2b.sh`), never over one that may still run.
2. `TaskStop` (or killing the shell) may not end the script's children, and an orphaned script carries on to its next
   line once the child it waited on dies. After stopping one, run `ff-leftovers list` and end every leftover of that run
   (`unity_slot.py run` waiters, `build_player.sh`, players).
3. Before the next push from that worktree, run `git log --oneline origin/<base>..HEAD`: it must hold only your commits.
   A script that makes temporary commits gets `trap '<reset>' EXIT INT TERM HUP`, so every way out puts the branch back.

**Why (w3826, 2026-11-09, lothlaptop slot1).** A background `build2.sh` built a HEAD player, then committed a TEMP revert
of #3471's code to build an A/B base player. Its build waited behind a person's editor for the Unity slot. The worker
stopped the task, rewrote `build2.sh` and started it again. The old script's orphan had lost the child it waited on, so it
went on, made the TEMP commit, and later re-read the rewritten file. `ff-pr push` then pushed the TEMP commit into PR #3482.
It was undone by a follow-up commit (no force-push), and two duplicate `build_player` waiters (one for the TEMP commit) had
to be found with `ff-leftovers list` and the process tree, then ended.

**How to apply.** Treat a background script like a running binary: new version, new name. Stopping it is not the end of
it until `ff-leftovers list` shows none of its children and `git log` shows none of its commits.
