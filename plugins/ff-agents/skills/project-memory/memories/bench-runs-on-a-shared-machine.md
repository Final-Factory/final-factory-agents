---
name: bench-runs-on-a-shared-machine
description: Timed bench legs on a machine other workers bench on too (BEAST, w1438) — a shared lock taken per run with a pause after each release, no editor start or editor tests while a timed run holds it, stop background scripts by process tree, check the save exists, and read BENCH-mode numbers from bench/summary.txt.
metadata:
  type: feedback
---

**Lessons from w1438 (2026-10-17, two workers on BEAST, worker a9560f02 option A and 40edc8fc option B).**

1. **One lock per machine, taken per timed run, released with a pause.** The two workers agreed on `F:/ffw/tmp/w1438-bench.lock`
   (`mkdir` is atomic; write an `owner` file "<sandbox> <session> <UTC time> <what>"; `rmdir` after). Every timed run,
   determinism leg, batch build and profile digest takes it. A loop that releases and immediately loops back to `mkdir`
   wins every time against a 15 s poll: mine held it 18:00-18:20 while the other worker never got in. Sleep 30-45 s after
   each release. Set an EXIT trap that removes the lock only after your `mkdir` succeeded, never before (a trap that
   always `rmdir`s can drop the other worker's lock).
   **BEAST's shared lock is now `F:/ffw/tmp/bench.lock`** (same `mkdir` + `owner` form), **and one older than an hour is
   taken as stale.** w1457 (2026-10-18) took it at 11:53Z for two builds, clips and then editor tests. w1459 replaced it at
   12:55Z while those tests still ran, so both ran at once. Release it between phases (builds, clips, editor), wait 30-45 s,
   and take it again. Never hold one lock across a long session.
2. **Your own editor counts as load.** Starting the sandbox editor, a force recompile or an editor test run while one of
   your (or anyone's) timed runs is in flight contaminated three of my runs (+3 ms each, measured: 84.0 against 87.0 ms
   on the same build). Hold the lock for editor compiles and tests too, or keep the editor stopped while legs run. A batch
   build also needs the editor stopped (same project) and must not see worktree edits until it finishes.
3. **TaskStop on a Git Bash background task ends only the wrapper shell.** The script it ran keeps going and keeps
   launching game players (three of my stopped A/B scripts kept starting runs, overlapping the other worker's bench).
   Stop by process tree: `Get-CimInstance Win32_Process`, match the script's command line, `Stop-Process` the bash
   processes, then check that no `finalfactory` player of that run is left (stop it by pid, never `ff-leftovers end`
   when an orchestrator forbids it).
4. **A save copy named after your temp folder (`ffa-<session>-<name>.zip`) goes when its request closes,** even when the
   same session carries on with the next request. A bench player given a save that is not there sits at the main menu
   until the probe's timeout (14 minutes a run), and the results look like a run. Check the file exists in
   `UserData/saves/` before a timed leg, and copy it again under the new request's name (compare its SHA-256 with the
   one you recorded).
5. **`scripts/bench/probe_ab_win_switches.sh` with `BENCH=1` prints an empty `round 1:` line.** The numbers are in
   `<run>/bench/summary.txt` ("idle 60s: ... frame p50 ... heartbeats N") and `save-idle*.csv`; tabulate those
   (`analyze_systems.py` for per-system times, `<before> <after>` for the movers).
6. **Measure the frames with no heartbeat too.** In single-player at most one heartbeat runs per frame, so the frame p50
   falls to the cheap frames only when the heartbeat frame plus one no-heartbeat frame fit in 62.5 ms. The bench's
   `-ffBenchFreeze 1` holds the simulation for its idle window (w1438: 23 ms p50 on Just Play), which sets the heartbeat
   frame a target needs.

Related: [[beast-shared-machine-perf-ab-side-by-side]], [[profile-a-save-top-systems]].
