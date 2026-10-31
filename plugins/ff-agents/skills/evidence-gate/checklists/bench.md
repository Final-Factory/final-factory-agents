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
- [ ] **A `timed_run` compares at most two builds** (w2419, 2026-10-27, tr_5a4f27fcf5): it accepted three builds and
      failed about two hours later with "more than 2 different builds". For three variants send two runs, base against
      each. `PerfSummary` has no heartbeat/other split, only all-frame avg, p95, p99 and fps; on JustPlay about 31% of
      frames are heartbeat frames, so p95 and p99 are heartbeat-frame numbers there, and `probe_table.py`'s fixed/hb
      column is the steadiest row for a change to a fixed-group system (w2419: spreads 0.01 to 0.03 ms against 0.10 to
      0.13 ms for the frame average).
- [ ] **A `timed_run` leg takes `-ff` switches only, not the automation channel's commands** (w2470, 2026-10-28): it
      refused `-ffAutomationPreConnectCommand`. A leg that must open a window or press something before the sample needs
      a switch the game reads at boot (w2470 used `-ffUiOpenBench`, which opens and closes the panels first). Check that
      the build you time has that switch: a build from before it ignores it.
- [ ] **Shortest run that answers the question.** The question and the smallest difference that would change the
      decision are written down. The legs, sample and settle are the shortest that can show it (a few percent: two
      rounds of 30 to 60 s on a quiet machine), and the round count is a cap.
- [ ] **A system's own work apart from its wait on other jobs** (w2256, 2026-10-26, Final-Factory/FinalFactory PR #2628).
      Timing a `SystemBase` whose `OnUpdate` calls `CompleteDependency()` (or any `JobHandle.Complete`), put a
      `ProfilerMarker` around that call and report the wait and own work (total minus the wait) as separate rows. On the
      Mall save on m3, 1.6 of LeechSystem's 4.8 ms per heartbeat in a raid was that wait for other systems' LocalTransform
      jobs. A profiler capture showed it moves into the next main-thread system that needs them (LocalPlayerMotionSystem's
      `JobHandle.Complete`) when the system no longer does it. So removing the wait does not speed up the frame, and an
      "Nx faster" goal is met (or not) on own work, with the wait stated beside it. Insert a probe marker at a line
      found by grepping its text (`grep -n "^      CompleteDependency();" | head -1`), never at a line number written down
      before later edits: a sed at a stale number broke the compile, and that timing leg ran the old assembly.
- [ ] **An editor leg times warm Burst code** (w2338, 2026-10-27, biscuit, Mall save, commit e947f566c4). A leg that
      starts a minute after an editor start can time jobs Burst has not compiled yet. Measured on one commit: LeechSystem
      0.623 / 3.317 ms per heartbeat at 6 / 20 Leeches one minute after a start, 0.158 / 0.193 ms in a warm pass. Both
      had Burst on, and the cold pass made the fix look slower than master (0.196 / 1.669 ms). Before the first timed leg, the leg's state line
      shows `BurstCompiler.Options.EnableBurstCompilation` true (a fresh editor once started with it off; turn it on and
      re-enter play mode), and the editor has run the scenario for a few minutes or one discarded warm-up leg. w2622
      (2026-10-31, m3 slot1): a sandbox editor had Burst compilation off, and an EditMode Performance test run right after a
      compile timed the spawn system at 11.8 ms per heartbeat, against 175 us once Burst had compiled it. Read
      `BurstCompiler.Options` before the ticket, and after every recompile (an A/B arm's code swap too) run one
      discarded warm-up.
- [ ] **A before/after: 1 or 2 samples per side, each run 5 to 10 minutes** (w2229, [lesson](../lessons/settle-your-own-guesses.md#decide-a-before-after-on-one-or-two-samples-per-side-w2229-2026-10-25);
      lothsahn: "workers should avoid more than 2 tests on each before/after unless there's a strong reason to suspect
      it's wrong. And each test should be short: 5-10 minutes at most"). A fix against master (fps, frame times, bench
      runs) is decided on 1 or 2 timing samples per side; a third needs a stated reason to suspect a result. Plan 1
      build per side, run alternating (A, B, A, B) in one exclusive session with the same leg sequence on both sides.
      After a move to another computer, time the baseline again there: timings never compare across machines (w2099:
      about 12 passes in an hour, repeated because the fix's run used another leg sequence and a reboot fell between
      the sides).
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
- [ ] **On a big computer, ask timed_place in this session before the ticket** (w1829, 2026-10-25). Its "here" verdict
      is per session: after a compaction or a resume, ask again before `bench_lock --timing`, or the leg dies at once
      with "w1995 ... Call timed_place" (it did, with the two load editors the demo had waited 9 hours for standing
      ready). A leg that must show this machine's own behaviour (a lock demo) passes `same_machine` with why.
- [ ] **A leg that must run on one named computer passes `machine`, never `same_machine`** (w2521, 2026-10-29). LothLaptop's
      G-SYNC panel, a GPU, an OS: `timed_place` with `machine: "lothlaptop"` (and why in `what`). It answers here only on
      that computer and otherwise queues the leg on it alone, saying it waits there; it never falls back to an idle or big
      one. `same_machine` means THIS computer: "Must run on LothLaptop" put there on biscuit heard "here" (w2448), and a
      what with no machine on an idle BEAST heard "here" too (w2501). Write the pin in the request's constraints as
      "Must run on <id> only" so start_agent, the queue and the room move keep it there (w2499 was moved to m3).
- [ ] **Reading an exclusive turn's quiet machine** (w1829, 2026-10-25). The `Unity.exe -adb2 -batchMode -name
      AssetImportWorker*` processes busy after a grant are the editors' import children and end with them; the
      holder's own sandbox editor rides along by design, even another session's. A close can stall on Unity's "Save
      Scene" dialog (slot3's load editor sat on it about a minute until it was force-stopped), so a demo or report
      checks each closed editor's pid is gone, not only closed.json.
- [ ] **Checking the turn's editor close on your own editor** (w2116, 2026-10-25). The holder's own sandbox rides along
      (`e.id !== h.sandbox`, ff-factory machine/benchTurn.ts), so take the ticket with `FF_SANDBOX_ID=<another name>` and
      `FF_SESSION_ID=` blank in the leg script: your editor closes like anyone's, and a sessionless holder leaves other
      workers' players running. Expect to wait: the queue gives running editors their 5-minute warning, and a sessionless
      ticket ranks "normal" behind them (16 min on BEAST). A `what` saying "no timing" is refused. Proof: the edit on disk,
      the pid gone, a new editor pid after the release (w2116: saved by t+9 s, gone by t+34 s, back 96 s after release).
- [ ] **A timed game run, not a harness test** (w1894, [lesson](../lessons/settle-your-own-guesses.md#hold-the-bench-lock-as-briefly-as-the-question-allows-w1628-2026-10-20)).
      Trying FF Factory's own bench, yield or priority code takes no real ticket: its unit tests or a queue under your
      `$TMPDIR`. An exclusive turn closes the machine's editors and ends other workers' batch builds.
- [ ] **The machine is yours while you hold it, and only then** (w1750). Your own players and clips pass the lock (the same `FF_SESSION_ID`, or inside `bench_lock`); other workers' are refused until you give it back, so give it back between legs. Not covered: a player already running when you were granted (your `quiet` gate waits for its CPU).
- [ ] **Nothing under the lock but the leg.** The Unity slot is taken before the ticket. Builds and digests run
      outside it, and the lock is given back between legs.
- [ ] **A GPU leg at the display's refresh rate is capped, not measured** (w2421, 2026-10-27, lothdesktop). A
      LightingBench/`zoom_run.sh` summary row at exactly the refresh rate (60.00 fps) with `present_wait_avg` near one
      frame (about 14 ms) and GPU ms near 13 was held by the display: from 16:11 every windowed player sat there, master
      and the fix alike, for over an hour, then it cleared by itself (310 fps, present_wait 1.07 ms at 16:58); cause
      unconfirmed (DISPLAY2 had dropped off the desktop). Before a series, one 5 s probe leg reads `fps` and
      `present_wait_avg`; during it, discard such a row and time only once present_wait is back near 1 to 2 ms.
- [ ] **Lock time reported.** The result says how long the run held the lock (`bench_queue.py report`).
- [ ] **At most two player builds of your own, and each leg checks its exe** (w1891, 2026-10-24). FF Factory's clean-up
  pass deletes a session's player builds beyond its newest 2 once they are untouched for 6 h (portal_logs, cleanup
  source, BEAST 2026-10-24T03:31Z: it removed devB and relB in the middle of a profiled A/B, and the whole A/B ran
  again). Delete the builds you no longer need as soon as you are done with them, rebuild instead of keeping a fourth,
  and have the leg script stop when a build's `finalfactory.exe` is missing, rather than time nothing.
- [ ] **A judder or feel report is traced on the person's own machine before any fix is designed** (w2448, [lesson](../lessons/settle-your-own-guesses.md#a-judder-or-feel-fix-is-designed-from-a-trace-on-the-machine-that-shows-it-w2448-2026-10-28)).
      Its screen, fullscreen mode, GPU and mods as the person plays: a FeelProbe trace of the bad and the good case and a
      profiler capture of the bad one. Read on-grid against off-grid frame intervals (intervals within 0.2 of a whole number of refreshes), the
      long frames' work, and a no-mods run. A model from another machine stays a guess until then.
- [ ] **One player per timed run, and a stopped loop is really gone** (w2496, 2026-10-29, LothLaptop). TaskStop on a
      background Bash command that runs a script loop ended the wrapper but not the loop: it went on launching players
      beside the next session, two `finalfactory.exe` per PresentMon window, and six runs were void. After stopping a
      background script, `ps -ef | grep <script>` and `ff-leftovers list` show nothing before the next timed session;
      before analysing, each run's presentmon.csv holds one ProcessID. w2507 again: TaskStop ended only the outer
      shell; the inner loops went on, restored settings and released the bench ticket mid-session, so stop the inner
      script pids too. A display, VRR or judder leg brings the game to the foreground and records the foreground
      process (G-SYNC is off for an unfocused game, measured w2507; the memory below has the recipe). A background Bash `timeout` is the run's limit
      (600000 = 10 min): give a multi-run session its whole length. PresentMon traps: [memory](../../project-memory/memories/presentmon-unelevated-timing-legs.md).
      A locked screen keeps every window out of the front: on a locked LothLaptop (LogonUI running, LockApp the
      foreground window) front.ps1 failed 6 tries and NVAPI read enabled=0 inVrrMode=0 (w2520, 2026-10-29, measured),
      so before a display leg `tasklist | grep -i LogonUI` shows nothing, else ask the person to unlock
      (`waiting_on_person`). `scripts/feel/vrr_trace.py record` writes about 3.3 GB per 6 s (trace.etl 674 MB,
      events.csv 2.6 GB, measured w2520): in a multi-run session delete those two after each run's summary.
- [ ] **Each arm of an A/B leg starts from the head's exact tree** (w2611, 2026-10-30, m3). `git checkout <commit> -- <path>`
      writes the index as well as the file, so a later `git checkout -- Assets` "between arms" puts back the swapped
      file, not the branch head, and the next arm silently times the wrong code. Reset every arm with
      `git read-tree -u --reset <head>` (restores, deletes and re-adds to the head's tree; `git read-tree -u --reset HEAD`
      at the end gives the sandbox back), and print each arm's `git diff --stat <head> -- Assets` into the run log.
