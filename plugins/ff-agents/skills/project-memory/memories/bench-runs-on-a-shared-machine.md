---
name: bench-runs-on-a-shared-machine
description: Timed bench legs on a machine other workers bench on too (BEAST, w1438, w1615) — the machine's first-come, first-served bench queue (bench_lock per leg, given back between legs, nothing waited for under it), no editor start or editor tests while a timed run holds it, stop background scripts by process tree, check the save exists, and read BENCH-mode numbers from bench/summary.txt.
metadata:
  type: feedback
---

**Lessons from w1438 (2026-10-17, two workers on BEAST, worker a9560f02 option A and 40edc8fc option B).**

1. **One queue per machine, taken per leg, given back between legs** (w1615, 2026-10-20; the w1438 `mkdir` lock with
   its 40-minute and one-hour stale rules is gone). `source scripts/bench/quiet_gate.sh`, then `bench_lock "<what>"`,
   `quiet`, the leg, `bench_unlock`; loop. The queue (`scripts/bench/bench_queue.py`, the game repo's
   `Documentation/Bench-Lock.md`) is first come, first served: a lock taken again joins the back, so a 20-leg A/B
   interleaves with other waiters, and no pause after a release is needed. Builds, batch compiles (`ff_unity_slot`,
   `unity-slot run`) and editor boots take shared tickets, which never run beside a leg. A ticket dies with its
   process, even under SIGKILL, so nobody takes over a live holder and nobody needs a keep-alive. A hold over 60 minutes
   is revoked, and `bench_unlock` then returns 2 with `Count this leg void`. `bench_status` (or
   `python scripts/bench/bench_queue.py status`) prints the holder and the queue in one line.
   **No waiting under the lock**: take a Unity slot before `bench_lock` (`ff_unity_slot --bench exclusive -- ...` does
   both, in that order), never inside it. Under the lock a slot or lab-lock wait is cut off at 2 minutes, and `quiet`
   gives the lock back after 15 minutes. Do a digest or a build after `bench_unlock`. Stopping a holding script frees
   its turn for the next in line, not for whoever polls first.
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
