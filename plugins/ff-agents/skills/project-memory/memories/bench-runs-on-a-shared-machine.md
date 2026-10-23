---
name: bench-runs-on-a-shared-machine
description: Timed bench legs on a machine other workers bench on too (BEAST, w1438, w1615) — the machine's first-come, first-served bench queue (bench_lock per leg, given back between legs, nothing waited for under it), no editor start or editor tests while a timed run holds it, stop background scripts by process tree, check the save exists, and read BENCH-mode numbers from bench/summary.txt.
metadata:
  type: feedback
---

**Lessons from w1438 (2026-10-17, two workers on BEAST, worker a9560f02 option A and 40edc8fc option B).**

0. **Timing in the editor needs the ticket too** (w1923, evidence-gate `lessons/every-timing-holds-an-exclusive-ticket.md`):
   a snippet that reads a clock (`unity-bridge.py eval_file ... --timed "<what>"`), MCP `execute_code` reads and a local
   Performance test run inside `python scripts/bench/bench_queue.py timed --what "<what>"` (in the background, then
   `timed --release`). Without one, `unity-bridge.py`, `unity_slot.py` and FF Factory's guard refuse it.

1. **One queue per machine, taken per leg, given back between legs** (w1615, 2026-10-20; the w1438 `mkdir` lock with
   its 40-minute and one-hour stale rules is gone). `source scripts/bench/quiet_gate.sh`, then `bench_lock --timing "<what>"`,
   `quiet`, the leg, `bench_unlock`; loop. The queue (`scripts/bench/bench_queue.py`, the game repo's
   `Documentation/Bench-Lock.md`) is first come, first served: a lock taken again joins the back, so a 20-leg A/B
   interleaves with other waiters, and no pause after a release is needed. Builds, batch compiles (`ff_unity_slot`,
   `unity-slot run`) and editor boots take shared tickets, which never run beside a leg. A ticket dies with its
   process, even under SIGKILL, so nobody takes over a live holder and nobody needs a keep-alive. **Turn limits** (w1832,
   enforced by the queue): while another worker waits, an exclusive turn ends at 30 minutes and a shared group an hour
   after its newest start; a 5-minute warning always comes first (the command output, and a message from FF Factory
   with your unpushed work: commit and push then). At the deadline the script and its players are stopped and
   `bench_unlock` returns 2 with `Count this leg void`; ask again and you go to the back. Nobody waiting, nothing ends. `bench_status` (or
   `python scripts/bench/bench_queue.py status`) prints the holder and the queue in one line.
   **No waiting under the lock**: take a Unity slot before `bench_lock` (`ff_unity_slot --bench exclusive -- ...` does
   both, in that order), never inside it. Under the lock a slot or lab-lock wait is cut off at 2 minutes, and `quiet`
   gives the lock back after 5 minutes. Do a digest or a build after `bench_unlock`. Stopping a holding script frees
   its turn for the next in line, not for whoever polls first.
   **Exclusive only for exact timings or the whole machine** (w1832, lothsahn: "request an exclusive lock if and only if
   they need the machine or exact timings. Otherwise they should use a shared lock": `--timing`, `--machine`, else
   `--shared`), **and as briefly as the question allows** (w1628, lothsahn: "A benchmark with 90%
   fidelity that runs twice as fast as better one is likely the right choice"). Never wrap a build in `bench_lock`:
   `build_player.sh` and `ff_unity_slot` queue a shared ticket themselves. Untimed heavy work (a determinism pair, a
   repro, a census) takes `bench_lock --shared`. The probe scripts quit 5 s after their sample (`DWELL`; before
   w1628 every leg idled `SETTLE + 2 x SAMPLE + 15` s under the lock) and stop at an even round once `ab_stop.py` calls
   the result clear past the noise. `bench_queue.py report` shows who held the lock and who waited. The evidence-gate's
   [bench checklist](../../evidence-gate/checklists/bench.md) is the pre-flight.
   **Short plans, a decision on enough signal, legs that fit the turn** (w1628, lothsahn: "Get them all to shorten their
   plans a lot", "if they have sufficient signal, just make a decision"): plan the fewest rounds, stop and decide once
   the answer is past the noise (the numbers and spread in the report), and fit each leg well inside the 30-minute
   turn; `report` flags a hold past it. **The queue's order** (w1628): the worker's request priority first, then one timed leg and one
   shared group in turn; a build joins the waiting group of builds or goes right after the next timed leg.
   **The priority hold** (w1860, lothsahn, 2026-10-23: "If a higher priority job holds the lock and all jobs below it are
   lower priority, it should retain the lock until done. If this is a shared lock, existing shared lock jobs should join
   it directly instead of queuing behind the exclusive lock"): the turn limits count only a waiter of your request's
   priority or higher. With only lower-priority work waiting you keep the lock until you let go (no warning, no revoke;
   the machine view says "keeps the lock"), so still give it back between legs: a same-or-higher waiter arriving later
   starts the usual clock, warning first. A shared group's priority is its highest running ticket's; while it outranks
   every waiting timed leg, new shared work joins it at once.
   **Every compute job holds a ticket** (w1860, lothsahn: "builds or any compute intensive job needs a lock... Shared if
   it's not performance sensitive and exclusive if it is"): a running sandbox editor holds a shared ticket for its whole
   life, and so does a game player started by `player_slots.py launch` outside your hold. Your leg's own sandbox editor
   and your own players ride along with your exclusive ticket; other sandboxes' editors and players hold it back up to
   the shared group's hour (warning first), so a timed leg on a busy machine can wait. While an exclusive ticket holds
   the machine, the daemon stops other sandboxes' batch Unity (builds, test runs), and `unity-slot run` ends its
   command and exits 75 when its own ticket is revoked: run it again. `Unity -batchmode` or `Unity -projectPath` typed
   straight into the shell is refused (`mcp__machine__unity` start, or `unity-slot run`).
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

7. **`timeout` around `scripts/bench/cpu_budget_run.sh` does not end its player** (w1590, 2026-10-20). The player
   `player_slots.py` launches is not in the timeout's process group, so a timed-out leg leaves `finalfactory.exe` running
   after you gave the lock back: two of mine ran 2 and 7 minutes inside other workers' holds (w1604, w1572). After every
   leg, ended or timed out, stop the pid the leg wrote in its `contention.txt`, and cut a leg early when its log floods
   (one dead entity reference logs a warning every heartbeat).

8. **The quiet gate can wait forever while another sandbox's editor works** (w1739, 2026-10-22, BEAST). `quiet`
   gives the lock back after 15 minutes and the leg queues again; with another sandbox's editor compiling and running
   tests at 1-5 cores, that loop lost 30 minutes twice and timed nothing. After one such give-back, run the legs with
   the gate off (`NOGATE=1` in the probe and cpu_budget scripts), keep each leg's `contention.txt`, and label the noise:
   release frame rounds then spread 2-4 ms (master alone 35.0-43.1 ms on JustPlay1003), so an effect of a few tenths of
   a ms needs the profile's job CPU (`CpuBudget` digest, 3.3 ms and both pairs agreeing) as its measure.

Related: [[beast-shared-machine-perf-ab-side-by-side]], [[profile-a-save-top-systems]].
