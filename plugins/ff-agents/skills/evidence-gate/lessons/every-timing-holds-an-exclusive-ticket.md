---
name: every-timing-holds-an-exclusive-ticket
description: "Every timing measurement holds an exclusive bench ticket on its machine, not only a bench script's leg: a snippet that reads a clock in the editor (unity-bridge.py eval/eval_file, MCP execute_code: Stopwatch, ProfilerRecorder, realtimeSinceStartup, in-job ProfilerUnsafeUtility.Timestamp counters), a Performance test run locally, a profiler capture you take numbers from. One call: unity-bridge.py --timed; across tool calls: bench_queue.py timed in the background, then timed --release. The game repo's unity-bridge.py and unity_slot.py and FF Factory's guard refuse the call without one (w1923, after w1892 timed a Burst job in its editor for an hour with none)."
date: 2026-10-23
---

# Every timing measurement holds an exclusive ticket (w1923)

**Rule.** If the number you are about to read is a time, hold an exclusive bench ticket on that machine while you take
it. That covers more than the bench scripts' legs:

- a snippet sent to your editor that reads a clock: `unity-bridge.py eval`/`eval_file` or MCP `execute_code`, with a
  `Stopwatch`, `ProfilerRecorder`, `realtimeSinceStartup`, `EditorApplication.timeSinceStartup` or `DateTime.Now`;
- in-job counters (`ProfilerUnsafeUtility.Timestamp` sums) that a snippet reads back;
- a `[Category("Performance")]` test run locally (MCP `run_tests`, `-runTests`);
- a profiler capture or `manage_profiler` frame timings you quote.

A build, a compile, a functional test or a determinism pair stays on its shared ticket, as before.

**Why.** lothsahn, 2026-10-23: "How is w1892 working on Lothdesktop if the lock is shared?", then "Why did it decide to
do that? How do we make sure workers aren't timing things without exclusive locks?"

w1892's worker spent about an hour (19:30 to 20:35 UTC, lothdesktop/slot4) timing an interleaved Burst-job
micro-benchmark through `scripts/unity-bridge.py eval_file ... bench.cs --no-safety-checks`, with no ticket, while three
editors held LothDesktop at 100% CPU. It reported "2.0 ms on the snapshot now that the machine is quieter", which is a
number from a machine it could not see. On BEAST the same day, w1893 timed its claims pass with in-job counters read
through `execute_code` the same way.

Nothing told either worker to take a ticket:

- The rules tied the exclusive ticket to bench scripts and players. Bench-Lock.md "Which ticket" read: "Only a run whose
  numbers are *times* takes an exclusive ticket (`bench_lock`)".
- This skill's bench checklist was titled "before a timed bench run".
- w1892's brief said "Bench lock only for timed legs".
- The FF Factory worker prompt said nothing about the lock.
- No tool looked at a snippet. The scripts took their tickets themselves, players checked the lock, and an editor that
  was already up took nothing for a snippet.

"Timed leg" read as "a bench script's player leg", so a micro-benchmark in the editor did not seem to need a ticket.
This reading comes from the rule files and the brief. The worker's own transcript was not read: the worker that wrote
this had no transcript tool.

**How to apply.**

1. Before the first timed read, take a ticket:
   - One call: `python scripts/unity-bridge.py eval_file --project-path <p> <file.cs> --timed "<what>"`.
   - Several calls, interleaved arms, or MCP `execute_code` reads: run
     `python scripts/bench/bench_queue.py timed --what "<what>" --minutes 20` with `run_in_background`, wait for its
     `granted` line, time, then run `bench_queue.py timed --release`.
   - A script of calls: `bench_queue.py run --mode exclusive --reason timing --what "<what>" -- bash <script>`.
   - A batch Performance run: `unity-slot run --bench exclusive --bench-reason timing -- ...`.
2. The usual bench rules apply. Keep it as short as the question allows. A turn is 30 minutes while someone waits,
   with a warning at 25. Give the ticket back between legs ([checklist](../checklists/bench.md)).
3. If a snippet reads a clock only for a timeout, say so with a `// ff-not-timing: <why>` comment (or `--not-timing
   "<why>"`). It runs without a ticket and is logged.
4. Put the ticket in the report next to the numbers (`bench_queue.py report`). A number taken without one is a guess
   about a busy machine. Label it so, or take it again.

**What enforces it** (the game repo's `scripts/bench/timing_gate.py`, FF Factory's `server/timingGuard.ts`):

- `unity-bridge.py` and `unity_slot.py` exit 6 on a clock or a Performance test with no exclusive ticket, before
  anything reaches the editor.
- FF Factory's guard refuses the same through MCP (`execute_code`, `run_tests`, `manage_profiler`) and from a branch
  whose `unity-bridge.py` predates the check.
- Every check is a line in the queue's `timing.jsonl`. `bench_queue.py report`, the machine view and `system_status`
  list the calls made outside a ticket.

Not caught by a tool: a snippet that only reads counters compiled into game code (w1893's case), and a player started
with its own timing flags outside a bench script. For those, the rule and the checklist line are the check.
