# Checklist: before any timing measurement on a shared machine (w1628, w1923)

Lesson: [hold the bench lock as briefly as the question allows](../lessons/settle-your-own-guesses.md#hold-the-bench-lock-as-briefly-as-the-question-allows-w1628-2026-10-20).
Mechanics: the game repo's `Documentation/Bench-Lock.md`.

- [ ] **Every timing holds an exclusive ticket, editor snippets included** (w1923, [lesson](../lessons/settle-your-own-guesses.md#every-timing-measurement-holds-an-exclusive-ticket-w1923-2026-10-23);
      lothsahn: "How do we make sure workers aren't timing things without exclusive locks?"). Before the first number
      that is a time, from a bench script's leg or from a snippet in your editor (`unity-bridge.py eval`/`eval_file`,
      MCP `execute_code`: Stopwatch, ProfilerRecorder, realtimeSinceStartup, in-job counters), a local Performance test
      or a profiler capture, you hold an exclusive ticket: `unity-bridge.py ... --timed "<what>"` for one call,
      `bench_queue.py timed --what "<what>"` in the background across calls (`timed --release` after), `--bench
      exclusive` for a batch run. The report names the ticket beside its numbers; a number taken without one is a guess
      about a busy machine (w1892: an hour of editor micro-benchmarks on a LothDesktop at 100% CPU, none held).
- [ ] **A whole-player A/B goes to a play-only timing machine when one is online** (w1946, lothsahn: "Can the portal do
      builds on one machine and then use this other with an exclusive lock for benchmarks?"; ff-factory PR #599). Two or
      more built Windows players timed on a save (probe_ab_win.sh's kind of run, numbers from `PerfSummary`): build them
      where you are, then call the worker tool `timed_run` (builds `[{name, path, args?}]`, save, rounds, sample_s,
      settle_s, res) instead of running the legs on your own busy machine. Your daemon sends only the pieces the portal
      lacks; the play-only machine (list_machines shows it, and no sandbox) plays the interleaved legs under its own
      exclusive bench ticket and sends back a `.tar.gz` in probe_ab_win.sh's layout with a mean ± SD table. End your
      turn with the wake_me it names; the results arrive as a message. Trust its numbers only beside its noise on the
      same build (two names for one build), measured. Editor micro-benchmarks still need an editor machine
      (`unity-bridge.py --timed`); a play-only machine has no editor.
- [ ] **Shortest run that answers the question.** The question and the smallest difference that would change the
      decision are written down. The legs, sample and settle are the shortest that can show it (a few percent: two
      rounds of 30 to 60 s on a quiet machine), and the round count is a cap.
- [ ] **A cost under a few percent is timed from inside, not by a whole-frame A/B** (w1780, lothsahn: "Measure the
      watchdog's own per-frame time first, then decide"). Eight m5 rounds of a whole-frame on/off A/B read the hang
      watchdog at 1.2% to 3.7% and could not settle it; an opt-in flag that timed its own step around the call
      (`-ffHangWatchdogSelfTime`, the game repo's `WatchdogCost`) read under 0.01% of frame time in two runs, even on a
      busy BEAST. Load only inflates such a self-timing, so a busy run is an upper bound. For "does X cost under N%?",
      add the flag (off by default, zero cost without it) before planning A/B rounds.
- [ ] **A short plan.** The fewest rounds that can answer the question (lothsahn: "Get them all to shorten their plans a
      lot"); the round count is a cap, never the plan.
- [ ] **Early stop on, and a decision on enough signal.** The probe scripts' `ab_stop.py` stop is left on, or the
      report says why `EARLY_STOP=0`. Once the data shows the answer beyond the noise, stop and decide (lothsahn: "if
      they have sufficient signal, just make a decision"), with the measured numbers and their spread in the report.
- [ ] **Each leg fits its turn; the queue enforces it** (w1832, lothsahn: "The harness should let workers run with
      the exclusive lock for at most 30 minutes. They should get a warning at 25 minutes. Once their turn is over, if
      they need more time they can apply for a new exclusive lock and they go to the back of the queue"). Plan each
      leg well inside 30 minutes and each build or shared job inside an hour, and give the lock back between legs.
      The queue ends a turn only while another worker waits behind it: an exclusive turn at 30 minutes, a shared
      group an hour after its newest ticket started once a timed leg waits. A warning always comes 5 minutes before,
      in the command output and as a message. At the deadline the ticket is revoked and the script and its players
      are stopped, and that leg is void. A re-request goes to the back of the queue. Exempt: the urgent release lane,
      the scheduled nightly, and a machine that hosts a single worker.
- [ ] **Priority counts** (w1860, lothsahn: "If a higher priority job holds the lock and all jobs below it are lower
      priority, it should retain the lock until done"). Only a waiter of the holder's request priority or higher starts
      its clock; with only lower-priority work waiting the holder keeps the lock until it lets go. That is no reason to
      hold it longer: give it back between legs anyway. A timed leg can wait behind other sandboxes' running editors
      and players, which hold shared tickets for their whole life (yours ride along), up to the shared group's hour.
- [ ] **At the warning, commit and push** the work-in-progress branch (lothsahn: "Workers should be encouraged to push
      their uncommitted work at the warning threshold so they can be scheduled on other machines").
- [ ] **The right ticket: exclusive only for exact timings or the whole machine** (lothsahn, w1832: "request an
      exclusive lock if and only if they need the machine or exact timings. Otherwise they should use a shared lock").
      `bench_lock --timing "<what>"` for a run whose numbers are times, `--machine` for one that needs the whole
      machine; everything else, including determinism pairs, repros, censuses, launch checks, installs and functional
      tests, takes `bench_lock --shared`. An exclusive ticket names its reason (`--reason`, `--bench-reason`); with
      none it is taken for timing and says so. A build takes no `bench_lock`, because its own `ff_unity_slot` ticket
      queues it.
- [ ] **A timed game run, not a harness test** (w1894, [lesson](../lessons/settle-your-own-guesses.md#hold-the-bench-lock-as-briefly-as-the-question-allows-w1628-2026-10-20)).
      Trying FF Factory's own bench, yield or priority code takes no real ticket: its unit tests or a queue under your
      `$TMPDIR`. An exclusive turn closes the machine's editors and ends other workers' batch builds.
- [ ] **The machine is yours while you hold it, and only then** (w1750). Your own players and clips pass the lock (the same `FF_SESSION_ID`, or inside `bench_lock`); other workers' are refused until you give it back, so give it back between legs. Not covered: a player already running when you were granted (your `quiet` gate waits for its CPU).
- [ ] **Nothing under the lock but the leg.** The Unity slot is taken before the ticket. Builds and digests run
      outside it, and the lock is given back between legs.
- [ ] **Lock time reported.** The result says how long the run held the lock (`bench_queue.py report`).
- [ ] **At most two player builds of your own, and each leg checks its exe** (w1891, 2026-10-24). FF Factory's clean-up
  pass deletes a session's player builds beyond its newest 2 once they are untouched for 6 h (portal_logs, cleanup
  source, BEAST 2026-10-24T03:31Z: it removed devB and relB in the middle of a profiled A/B, and the whole A/B ran
  again). Delete the builds you no longer need as soon as you are done with them, rebuild instead of keeping a fourth,
  and have the leg script stop when a build's `finalfactory.exe` is missing, rather than time nothing.
