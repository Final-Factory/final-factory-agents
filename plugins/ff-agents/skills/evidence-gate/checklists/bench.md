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
- [ ] **An editor timing loop goes in chunks of a few seconds per `execute_code` call** (w4016, 2026-11-12: 220
      iterations of `DeterminismStateFingerprint.Compute`, 0.3-0.45 s each, is minutes in one call; a call past about
      10 s times out at the bridge, keeps running, and can run twice). Samples accumulate across calls in
      `AppDomain.CurrentDomain.SetData` under a round label with a done-counter; editor-ops, "Timeout receiving Unity response".
- [ ] **A time in a before/after table is the median and spread of several runs per side, on an exact clock** (w4017,
      2026-11-12: a one-run table read a quiet AutoQuit at 0.47 s before and 1.09 s after, and Ben asked whether the fix
      slowed the quit; 8 interleaved runs each, timed from the log line to the process's own ExitTime, read medians
      0.58 s with the fix and 0.56 s without it, host, spreads 0.03 to 0.09 s). Interleave the builds (ABBA), hold the ticket above, and time with the process's ExitTime
      (`GetProcessTimes`) or an in-game stamp, never a `tasklist` or log poll loop (about 0.5 s of slop). A number from
      one run per side is labelled "one run, not comparable" or left out of the table.
- [ ] **A ticket is held only by a turn or a background task you watch** (w3715, lothsahn: "make sure stuff holding
      locks can continue doing stuff"; "it shouldn't be idle and hold the lock"; ff-factory PR #913). Run
      `bench_queue.py timed` and the legs under it in this turn or in a Bash `run_in_background` task, never behind
      `nohup`, `setsid` or a detached script, and release the ticket the moment the legs end. FF Factory lets a holder's
      messages and wake_me through machine holds, the agent cap and the usage limit, and fires its wake_me as soon as its
      last ticket goes. A holder with no turn and no background task running is warned after 2 minutes, and 10 minutes
      after the warning its ticket is revoked (bench_queue.py's own revoke, then the helper's tree 90 s later): w3536's
      probe held LothDesktop's ticket for about an hour on 2026-11-08 while its worker sat idle behind a hold.
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
- [ ] **A player A/B's first leg can be a warm-up outlier on a laptop** (w3335/w3638, 2026-11-08, LothLaptop, RTX 4070
      Laptop, Wittlebase3 roam, ABBAAB). Run 1 (1.0.0.30) read median frame 6.4 ms / 135.8 fps; the five later runs of
      BOTH builds read 8.9 to 9.2 ms / about 98 fps. Its main-thread p50 matched theirs (6.1 against 6.2 to 6.5 ms) and
      its GPU p90 did not (2.9 against about 6 ms), so it was the GPU or power state, not the build. Pooled, it made
      1.0.0.30 look 12 fps faster. Run one discarded warm-up leg first, or check leg 1 against the same side's later legs
      and set it aside when it is out of line with both sides; say so in the report.
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
- [ ] **A per-event cost is weighed at the real event rate, not the synthetic one** (w3955, 2026-11-12, BEAST and
      lothdesktop). A log written per enemy hit cost +26% of `IncomingHealthChangeSystem` at a synthetic 8,000 hits a
      heartbeat (about 110 ns a hit), but real saves counted 0 to 0.03 enemy hits a heartbeat, and the whole-frame player
      A/B (timed run tr_89ab62e413) showed no difference. Before timing, count the event rate on two or three real saves
      (a counter the change already keeps, read in play), and bound the share as the added % of the system times the
      system's share of the heartbeat frame (the game repo's `Documentation/Performance-JustPlay-Transform-Chain-Waits-2026-10-27.md`
      has job lengths, e.g. `IncomingHealthChangeJob` 0.42 of 39.3 ms on JustPlay1003).
- [ ] **A cost timing runs on a world that holds what the change's cost grows with** (w4012, 2026-11-12; the
      orchestrator for ben: "its JustPlay save has 0 TeslaArcItem, 0 RemotePowerProducer and 0 StationGrid entities, so
      it never timed the part of your change that grows with Tesla grids"). w4016 timed w4012's fingerprint change on
      JustPlay (1,477,843 entities) and measured only the fixed part (+2.3 ms). Before a timed leg, count in the chosen
      world the entities the change's new work iterates. Where no save has them, build an `EcsTestBase` world scaled in
      N (100, 1,000, 4,000) in a `[Category("Performance")] [Explicit]` test that times with the data, stripped, and
      with it again (the game repo's `PowerTeslaFingerprintCostPerformanceTest`; w4024 on the m3 measured +0.145,
      +0.477 and +1.762 ms median), and report the per-entity cost with an estimate of the count a large base reaches.
- [ ] **A "battle save" is checked for its battle in player.log** (w3955, 2026-11-12). The LifeAsTwoMegaWave fixture
      loses its wave on 1.0 builds: `Step0_50_0_55ClearAttackWaves` removes its 1,433 attack-wave ships on load, leaving
      52 enemies. Grep the leg's player.log for `Removed .* attack-wave ship` (and count enemy hits) before calling a
      save a battle save in a PR or report.
- [ ] **A short plan.** The fewest rounds that can answer the question (lothsahn: "Get them all to shorten their plans a
      lot"); the round count is a cap, never the plan.
- [ ] **Size the biggest leg with a short probe before the series** (w3094, 2026-11-04, m3). A briefed plan of 12
      `ffu-headless phases` runs came to ~21 h of exclusive bench: a 50-tick probe measured trident:20000 at 11.1 s a
      tick, so one 2000-tick run was 6 h or more. Probe the biggest leg (a few ticks or seconds), multiply it out, and
      when the plan will not fit a sitting, report the probe with a reduced plan to the requester before starting it
      (w2895's answer: 100 ticks of the big camps, 3 rounds only of the small ones). Run a leg over ~10 min detached
      (`nohup bash leg.sh &`) with a `wake_me`, never as a Claude Code `run_in_background` Bash job: that job is killed
      at its time limit (2 h at most) and its child with it, which lost a 2 h leg here.
- [ ] **Early stop on, and a decision on enough signal.** The probe scripts' `ab_stop.py` stop is left on, or the
      report says why `EARLY_STOP=0`. Once the data shows the answer beyond the noise, stop and decide (lothsahn: "if
      they have sufficient signal, just make a decision"), with the measured numbers and their spread in the report.
- [ ] **Each leg fits its turn; the queue enforces it** (w1832, lothsahn: "The harness should let workers run with
      the exclusive lock for at most 30 minutes. They should get a warning at 25 minutes. Once their turn is over, if
      they need more time they can apply for a new exclusive lock and they go to the back of the queue"). Plan each
      leg well inside 30 minutes and each build or shared job inside an hour, and give the lock back between legs.
      For `bench_queue.py` tickets, the queue ends a turn only while another worker waits behind it (a `timed_run`
      gives its lock back after 24 minutes regardless, w3711): an exclusive turn at 30 minutes, a shared
      group an hour after its newest ticket started once a timed leg waits. A warning always comes 5 minutes before,
      in the command output and as a message. At the deadline the ticket is revoked and the script and its players
      are stopped, and that leg is void. A re-request goes to the back of the queue. Exempt: the urgent release lane,
      the scheduled nightly, and a machine that hosts a single worker.
- [ ] **A `timed_run` fits one lock: 10-minute legs, 2 rounds, then a new run** (w3711, 2026-11-08, lothsahn: "106
      minutes is super long. It should do 10 minute samples and run no longer than 30m per lock"). w3639's
      tr_dadec6ac06 asked for 4 builds x 2 rounds at sample_s 180; the tool answered "its bound is about 106 min" (every
      leg at its timeout, plus 20) and the worker and orchestrator read that as how long it held the lock; it planned
      about 31 min of legs (measured, about 233 s each). The tool now refuses a leg planned past 10 minutes (90 s launch
      and load, settle, sample, dwell), and, unless `reason` says why in a sentence, more than 2 rounds or more legs
      than one 24-minute turn plays. More samples are a NEW `timed_run` afterwards, which queues at the back. Quote its
      answer's play time ("It plays about N min of legs"), never the bound. The timing daemon gives the ticket back
      after 24 minutes of legs whether or not anyone waits (the queue's own "only while another worker waits" rule is
      for `bench_queue.py` tickets, not `timed_run`), and queues the rest again at the back.
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
- [ ] **No CI job beside the timing** (w3112, 2026-11-04, for ben: on m3, exclusive ticket t00001116 timed FFU while
      the Mac's GitHub Actions runners ran jobs from 15:35 to 16:09, load average up to 24.1 against about 2 idle).
      Runner.Listener processes are the idle baseline; a running Runner.Worker means a CI job is active. The grant
      waits out a running job (20 min at most) and the daemon pauses idle listeners on macOS and Linux (Windows: waited
      out only); a timing whose history `ci` event says `gave_up`, or names `busy_runners`, ran beside CI: say so beside
      its numbers. Mechanics: the game repo's `Documentation/Bench-Lock.md` "No CI job beside a timed run".
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
      An arm built from another commit's whole tree is built in the sandbox at that commit, one commit at a time
      (`switch_branch` with create_from, build, move the player out, the next). Never a clone of the game repo: the
      guard refuses one and the retired `scratch_clone.sh` (w3703: such clones reached 43 GB on V:).
- [ ] **A script holding `bench_queue.py timed` in the background starts timing on `granted tNNN: time now`, never on
      "granted"** (w3158, 2026-11-06, biscuit). `bench queue: tNNN: granted (exclusive)` prints first, then the grant
      waits up to 20 min for CI jobs (w3112), and that wait counts against the 30-minute turn: a `grep -q granted` leg
      started at load 69 beside 4 ffu CI jobs, and three later turns spent their whole 20 minutes in the CI wait. Wait for
      the `^granted .*time now` line, note when the first grant line came, and run a leg only with its length left in
      the turn (grant + 30 min), else give the turn back; record the ticket log in each leg's folder.
- [ ] **A pair-run leg has its ticket before the GO, and `ff-leftovers end` only after its last timed leg** (w3414,
      2026-11-07, biscuit client of a LothDesktop host). On a big computer (biscuit, BEAST, LothDesktop) `bench_queue.py
      timed` first needs `timed_place` (with `same_machine` naming the pair run), then the grant can still wait up to
      20 min for CI jobs: start both as soon as the run is planned, never after the host's GO (the first JustPlay1003
      join launched 5 min late and the host's window ran out). Hold the ticket wait with `run_in_background`, never a
      foreground until-loop: a blocking call hid the next GO for 6 min. `ff-leftovers end` ends every background job of
      your session, your own `bench_queue.py timed` holder included, so ending a finished player between joins dropped
      the ticket twice; re-take it at once, or let the player end by its own timeout.
- [ ] **A network latency leg from a Linux host on Wi-Fi checks the radio before blaming the network** (w3925,
      2026-11-11, biscuit: ping p99 to the router 409 ms, then 12-17 ms after the fixes). Read
      `iw dev <if> get power_save` (on is the NetworkManager default), `iw dev <if> link` (which mesh node and its
      signal: biscuit roamed to a 6 GHz node at -72..-80 dBm with a 5 GHz node at -62 beside it), and
      `timeout 120 stdbuf -oL iw event -t > file` for periodic `scan started` lines: each full-band scan stalls traffic
      for 6-8 s. GNOME Settings left open on its Wi-Fi page scanned every 15.0 s (measured); below about -70 dBm the
      background scan ran about every 30-37 s. Fixes for the session only, after the person's go:
      `nmcli con modify --temporary "<ssid>" 802-11-wireless.powersave 2` or `802-11-wireless.bssid <node>`, then
      `nmcli con up "<ssid>"` (a few seconds' blip; wait for CI jobs to end). Split the path first: ping the router from
      the host itself, so the far machine's own Wi-Fi (m3 lost one ping every ~9.4 s on 6 GHz) is not counted twice.
