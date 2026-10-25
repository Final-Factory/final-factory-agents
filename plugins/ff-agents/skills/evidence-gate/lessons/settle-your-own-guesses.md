---
name: settle-your-own-guesses
description: "The evidence gate is self-enforced. An agent settles a guess by research or measurement and then proceeds; the person is asked only for money values, for what the rules reserve for them, and for a fork research could not settle. A CI job that died at its timeout or with every test green is read before it is re-run. A bulk read of GitHub history takes the cheap path and stays well inside the account's shared API budget. A crash with only GPU-driver frames is not \"nothing to fix\" until the driver is dated, the CPU read from the dump, the game step that fed it measured and a guard looked for. A timed bench run holds a shared machine's lock only as long as its question needs: the fewest rounds that can answer it, a decision as soon as the signal is clear, the exclusive ticket only for timed numbers, at most one hour per hold (w1628)."
date: 2026-10-02
---

# Settle your own guesses

**Rule.** A guess on a choice that affects the outcome is yours to settle: research it or measure
it, record the basis, and carry on. "The person decided" is not a way out of research.

Ask the person only for:

1. **Money:** the value (a budget, a bid, a purchase), once per decision, with the evidence shown.
2. **What the rules already reserve for them:** deletes, app settings and deploys, publishing in
   their name, releases. Merging your own verified work is not on the list: later the same day Ben
   added "stop holding prs, just merge them" ([merge your own pull request](merge-your-own-pr.md)).
3. **A real fork research could not settle:** the options, with a recommendation.

**Why.** Ben, 2026-10-02, on the first design of this gate, which let a guess be resolved by
escalating it: "I want the agent to be mostly autonomous. i dont want you to run every decision
by me. i just want YOU to make sure you are making decisions with appropriate context and
research. If its spending actual money then yea, ask me to confirm the value."

The Reddit campaign went wrong while Ben was approving things: he said yes to caps he had no way
to judge. More questions to him would not have helped. Research by the agent would have.

**How to apply.**

- The record stays a few lines and is never a questionnaire for the person.
- When a row is a guess, the next step is research, in this order: the tool's own docs, the value
  its screen shows, our own data, other people's write-ups, a small reversible test.
- When you do ask about money, show what the value rests on beside the ask.
- An orchestrator that receives a guess from a worker sends it back to be researched. It does
  not pass the question to the person.
- Reports still label each number and recommendation measured, sourced or guess, so the person
  can see what a result rests on without being asked to decide it.

## When a measurement cannot resolve it, measure closer to the change (w824, 2026-10-09)

A measurement whose spread is wider than the difference you must judge settles nothing: neither escalate on its
noise nor merge on a hunch. Measure the changed code itself, as an upper bound, and measure the case that triggers
it. w824 (PR #1332, the vision fingerprint skipping blueprint-preview children, a class 3 FFBox desync PR): the
2-peer JustPlay bench on BEAST, 4+4 interleaved runs, gave host heartbeat means of 123.3 ± 3.6 against
125.3 ± 9.4 ms, a standard error of 5 ms on the delta against a 1% threshold of 1.2 ms (about 280 runs would have
resolved it). Timing `PrepareC3VisionChunks`, the only main-thread code the change adds, on JustPlay in the editor
(1.08 ms median over 50 calls, once per 8 heartbeats) bounded the change at +0.11% tick mean, +0.63% p95 and +0.57%
frame median. Timing the vision hash with a held preview found a cost the bench could never show: 47.6 against
42.6 ms, every one of 45,566 holders paying a hash-set lookup; the review limited it to Parent-bearing chunks (49.9
against 50.0 ms after). The steps for class 3 PRs are in `checklists/ffbox-desync-pr.md`.

## A speed-up is one build, switched off and on, back to back (w1069, 2026-10-13)

A run from earlier is not a baseline on a shared machine: other editors, builds and players come and go between the
two runs. **Rule.** Measure a performance change as the same build with the change switched off, then on (then off or
on again), back to back on the same machine, and check that a system the change does not touch reads the same in
both, within about 10%. If it moved, the machine moved, and the comparison says nothing. w1069 step 6 (PR #1635, a
chunk index for the Supply Bots' source-container search): against the step 5 bench run 35 minutes earlier, the
assigner looked 2.3x faster at 10,000 bots (16.4 against 7.2 ms), but the bot-task system, which the change never
touches, was 40% faster too: three editors and a player build had shared the machine during the earlier run, one
editor during the later. The same build with the index switched off, run between two runs with it on, gave 9.33
against 7.25 and 7.45 ms: about 20%. A switch for an A/B can be a temporary edit you revert, never a committed
toggle.

### Before every leg: nothing of yours is still running (w1258, 2026-10-14)

- `TaskStop` on a background `bash` wrapper does not stop what it started: the loop script (`probe_ab_win_switches.sh`) and its
  `finalfactory.exe` keep running. Worker 28ebd585 found two "stopped" loops still running 40 minutes later, which made its whole
  Deck-paced frame A/B unusable; the next worker on BEAST hit it again. Before the next leg, list `Get-CimInstance Win32_Process`
  for the script's name and `Stop-Process` the script and the player.
- Your own searches count: a `find /` started minutes earlier ran three cores at 100% inside the first A/B run. Run
  `ff-leftovers list` first, and read the run's `contention.txt` for other sessions' processes (the quiet gate waits for their
  players and batch builds, not for their `find`s).
- A script that rewrites the perf doc on Windows reads and writes explicit newlines: `core.autocrlf` checks the doc out with CRLF,
  so anchors like `'## Ranked weak points
'` do not match; write with `newline=chr(10)` so the blob stays LF.

## An A/B on one machine: check the thing happened, and run both builds at once (w1329, 2026-10-15)

w1329 (the Technology window's open cost on Life's save) ran master and the fix as two game players on beast at the same
time. The tour opened the window with the T key, and only the focused window gets keystrokes: neither client ever opened
it, its "open" frames showed no spike, and the table looked like a result until the log was read. Sequential runs on the
same shared machine swung more than the effect under test: one build's closed-window frame read 27-28 ms in two runs and
48.9 ms in a profiler capture half an hour later, the other 32-36 ms and 32.7 ms.

- **Prove each measured action happened**: open panels by the automation command (`ffauto:ui.open|<panel>`), never a key,
  when more than one game window is up, and find the line that says it did in the run's log (`opened panel 'research'`)
  before reading any number.
- **Run before and after together, then swap**: two players at once, each pinned to its own CPU set
  (`(Get-Process -Id <pid>).ProcessorAffinity`), then again with the sets swapped, so machine load and core speed cancel.
  A difference that flips sign when the sets swap is the machine's, not the change's.
- **Name the per-marker cost** of what the change leaves running (a profiler log of a few seconds, `profile:<name>` in the
  Deck tour), and say a frame-time gap smaller than the run-to-run swing is not measured.

## Hold the bench lock as briefly as the question allows (w1628, 2026-10-20)

**The rule.** lothsahn, 2026-10-20: "Workers should also consider how they can hold a bench lock as short as possible.
A benchmark with 90% fidelity that runs twice as fast as better one is likely the right choice." Before you take a
machine's bench lock, pick the shortest run that still answers your question. That means the fewest and shortest legs
that can show the difference you are after, an early stop once the result is clear past the noise, and no re-run you
do not need. Only a run whose numbers are times takes the exclusive lock. Untimed heavy work takes a shared ticket
(`bench_lock --shared`), and a build takes nothing extra.

lothsahn, later the same day: "Get them all to shorten their plans a lot" and "And if they have sufficient signal, just
make a decision". So plan the fewest rounds that can answer the question, and stop and decide as soon as the data shows
the answer beyond the noise, with the measured numbers and their spread in the report. And: "We should request workers
subdivide their work to not hold the exclusive lock longer than 1 hour at a time too." Since w1832 (2026-10-23) the
queue enforces a shorter rule itself: "The harness should let workers run with the exclusive lock for at most 30
minutes. They should get a warning at 25 minutes", pre-emption "should not occur if there's no other workers waiting
in line", and a shared group ends an hour after its newest start once a timed leg waits, always after a 5-minute
warning. Give the lock back between legs or rounds and queue again; at the warning, commit and push your work.

**Why.** On 2026-10-20 (00:00 to 15:58 UTC, measured from each machine's transcripts and run logs; the game repo's
`Documentation/Bench-Lock.md`):

- BEAST's lock was held 15.5 of 16 hours, and requests spent 40 hours waiting in its queue (not counting waits behind
  their own legs).
- lothdesktop's lock was held 12.7 hours, with 14.3 hours of waiting.
- lothsahn: "Timed runs are killing our throughput... Our workers have become almost serial instead of parallel."

Where the time went:

- **Builds under the exclusive lock.** They held it for 1.7 h on BEAST and 3.7 h on lothdesktop (one release build
  held it 58 minutes). Determinism pairs and repros held it for another 1.3 h and 1.1 h.
- **An idle tail in every probe leg.** The player's dwell counts from the end of its command chain, but the probe
  scripts asked for `SETTLE + 2 x SAMPLE + 15` s more: 120 s of nothing per leg at the defaults. With a 240 s settle
  and 90 s sample, legs ran 810 to 824 s until the backstop killed them.
- **Rounds past the answer.** w1243's radius A/B queued 20 legs of 746 s each. Its two arms were apart by 0.5 ms
  against a 0.17 ms spread after two rounds; stopping there would have freed about 3.3 hours of BEAST.

**How to apply.**

1. Write the question and the smallest difference that would change your decision before the first leg. A
   difference of several percent shows in two rounds of 60 s on a quiet machine (BEAST repeats to about 1 to 2%).
   A 1% question on a busy machine needs a closer measurement (the per-system time, a timed call), not 20 rounds.
2. Leave the probe scripts' early stop on (`scripts/bench/ab_stop.py`; `EARLY_STOP=0` only when you can say why).
   Use an even round count as the cap, not the plan.
3. Keep legs short: a settle long enough for the event you measure, a sample of 30 to 60 s, and no longer.
4. Untimed work (a determinism pair, a functional repro, a census, a Steam launch check) takes
   `bench_lock --shared`. A build takes no `bench_lock` at all, because `build_player.sh` and `ff_unity_slot` queue
   their own shared ticket.
5. Give the lock back between legs, and do builds and digests outside it.
6. After the run, `python scripts/bench/bench_queue.py report` shows your holds and whom they kept waiting. Put the
   lock time beside the result in your report.
7. Plan each exclusive hold to end within an hour: split a long run into holds of an hour or less, each given back
   (`bench_unlock`, then `bench_lock` again, which requeues you). Past an hour `bench_unlock` warns you, `bench_status`
   shows the hold over the rule, and `report` flags it with your request; nothing kills your leg for it.
8. Decide on enough signal. Once every arm's gap is clear of the run-to-run spread (or all are inside the noise), stop
   and write the decision with the numbers and the spread; more rounds are for a question the data has not answered
   yet, not for confidence in one it has.
9. A harness test takes no real ticket (w1894, 2026-10-23). Trying FF Factory's own bench, yield or priority code is
   not a timed run: use its unit tests (ff-factory `server/benchTurn.test.ts`, `server/personPlay.test.ts`, with fake
   procs and editors), a bench queue under your own `$TMPDIR` that nobody else reads, or a throwaway process tree for
   an OS fact (a lowered priority reads back as Idle and is inherited by children started under it). A worker on BEAST
   took exclusive ticket t00000849 for a priority A/B; the turn ended another worker's batch build in beast/slot2
   (w1826's host player build, which a two-machine check waited on). The orchestrator, for lothsahn: "Your work is FF
   Factory code, not a timed run. Don't take real exclusive tickets on BEAST. Exercise the yield and priority logic
   with unit tests, or with a lock instance in your own temp folder that doesn't pause other workers." A real
   before/after the request needs belongs to its live check, on the machine it names, when that machine is free.

## Every timing measurement holds an exclusive ticket (w1923, 2026-10-23)

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

## An equivalence test of a pruned search puts a tie on each bound, and fails on the flip (w1069, 2026-10-13)

An index or a pruned search that must pick exactly what a full scan picks (a different pick is a different trip, and
on a peer that scans, a desync) is only tested where its prune can be wrong: at equality. **Rule.** For each bound
the search stops or skips on, add a case whose candidate sits exactly on that bound (the bound's nearest point, with
the bound's best value) and ties the best score while winning the tie order. Then flip the bound's comparison (`>` to
`>=`) and see the test go RED before you call it covered. w1069 step 6: five random worlds of 1 to 400 containers and
a hand-built tie case all passed with both prunes flipped, because none of their ties fell on a bound; only
`NetworkedProviderIndexTest.ATieOnTheBound_OfTheNextChunk_StillWins` (origin on a chunk's first tile, the tied
container one tile across the border with the item's largest stock) failed on the flip and passed on the real code.

## Read why a CI job died before re-running it (w906, 2026-10-10)

A re-run on a guess is acting on a guess. **Rule.** Before re-running a job that was cancelled at its timeout or failed with every test green, find out which
of these it was, and say it in your report:

1. **No log at all.** `gh api repos/<o>/<r>/actions/jobs/<id>/logs` answers `BlobNotFound`, earlier steps
   included, and the cancel took the full grace (`completed_at` 5 min after the timeout). The job **lost its runner**;
   no test was slow. GitHub's hosted Windows runners do this on their own (actions/runner#4632, about 5% of long
   Windows jobs there), and so does anything that ends the runner's processes. ff-factory re-runs such a job once
   (`.github/workflows/rerun-lost-runner.yml`).
2. **A log, cancelled at the timeout.** A test hung. Read which: ff-factory runs its unit tests under
   `scripts/test-watchdog.ts` with `scripts/test-inflight-reporter.ts` and `--test-timeout`, which print the running
   tests and the processes under them before the job's timeout. A test file listed with no test under it is a process
   that does not exit (an open handle). In another repo with no watchdog, add one before the second re-run.
3. **`coverage file is empty`, every test green** (`node --test --experimental-test-coverage`). A node process
   carrying `NODE_V8_COVERAGE` was ended while it wrote its coverage at exit. The file's name is
   `coverage-<pid>-<ms of the write>-0.json`: match the pid and time to the process (a Windows process trace) and the
   test running then.

**Why.** w906, 2026-10-10 (ff-factory "Typecheck, unit tests, build (windows-latest, 1/2)"):

- Two jobs hung to their 15-min timeout and lost their entire log, and a worker re-ran one without knowing why. Two
  causes fit:
  - GitHub's own runner losses;
  - `Stop-FFDaemon` collecting a process's children by Windows `ParentProcessId` alone. Ids are reused and a dead
    parent's id is never cleared: on a runner, wininit.exe's dead parent id was seen drawn by an OpenConsole.exe. A walk
    that met it would end services.exe's tree with the runner in it.
- "Coverage file is empty" failed 27 runs in 30 days (measured). The cause was a deploy probe's
  `& node -p ... | Select-Object -First 1`: PowerShell ends node as soon as it has the first line, often mid-write.
- An earlier fix deleted `NODE_V8_COVERAGE` from the child's env, and node put it straight back: `child_process`
  copies it into any env that lacks the key.
- Two traps hit the investigation itself. A probe that walked *up* the process tree with no visited set looped forever
  on a reused id: a 461 MB log, four frozen jobs first misread as runner loss. And a test that read a pid file before
  it was written got pid 0; on Windows, node ending pid 0 ends the caller (libuv `uv_kill`), so the test file died
  silently.

**How to apply.**

- Read the job's log, annotations and step timings (`gh api .../actions/jobs/<id>`) before any re-run.
- A re-run is allowed only alongside a named cause.
- To keep a child out of coverage, set `NODE_V8_COVERAGE: ''`; never delete the key.
- Collect a native program's output before cutting it short (`(& node ...) | Select-Object -First 1`).
- A walk down a Windows process tree takes a child only when it started no earlier than its parent; a walk up keeps a
  set of the ids it has seen.
- Never end a process by an id parsed from a file without checking that it is above 0.

## Read GitHub history the cheap way, well inside the shared budget (w1175, 2026-10-13)

Every agent on an account shares one GitHub REST budget, about 5,000 calls an hour, and so do the account's CI
tools. A survey that spends it stalls everyone else's `gh` until the hour resets. **Rule.** Before a bulk read of
GitHub history (CI runs, jobs, logs, PRs over weeks), count the calls it will make, sample when that is more than a
few hundred REST calls, and take the cheap path:

1. **The run list one day per query.** `actions/workflows/<id>/runs?created=<day>&per_page=100` returns at most
   1,000 runs per query whatever the range, silently. Keep each run's `node_id`.
2. **Job results through GraphQL, 50 runs a query** (`nodes(ids: [...]) { ... on WorkflowRun { checkSuite {
   checkRuns(filterBy: {checkName: "<job>"}) { conclusion startedAt completedAt steps { ... } } } } }`, cost 1
   each). GraphQL's hourly budget is separate from REST's.
3. **Failed test names from check-run annotations, not log downloads.** A results check run (FinalFactory's
   `editmode Test Results`) carries one annotation per failed test; a log is one REST call per job.
4. **The job's own annotations name an infrastructure failure**: `upload-pack: not our ref` is a commit gone before
   checkout, a quick `exit code 1` with no results a compile error, `exit code 139` a segfault.
5. **The budget of the token you actually spend.** `gh api rate_limit` can answer `remaining: 5000` while your calls
   get 403: read `X-RateLimit-Remaining` from a real call's headers (`gh api -i <endpoint>`), and stop when it falls
   to about 1,500: the portal's pollers (an estimated 25-40 calls a minute) and every other worker spend from the same
   budget (w1185). `gh api rate_limit` gave the false 5000 five times that night, on beast and on lothdesktop.
6. **Two calls at a time, not eight.** `xargs -P 8` or `ThreadPoolExecutor(8)` empties the hour in minutes, before
   any header check can stop it.
7. **No gh poll loops.** A wait for CI is `blocked_on` with `ci:<owner/repo>#<n>`. An `until gh run list …; sleep 15`
   makes about 400 calls an hour and keeps calling after the limit (w1185: 153 refusals in 25 minutes). When refused,
   stop every gh call until the 403's `X-RateLimit-Reset`.
8. **A question about money or minutes starts at the bill, not the run history.**
   - `gh api "organizations/<org>/settings/billing/usage?year=Y&month=M"` gives one line per day, SKU and repo; `.../usage/summary` gives the month's totals. Four calls cover four months, and Ben's `bryding` login, an org admin, reads them.
   - Read `netAmount`: only that is billed. `grossAmount` minus `discountAmount` is the free part: a public repo on standard hosted runners, self-hosted runners, and the plan's included minutes.
   - The old `orgs/<org>/settings/billing/actions` and `/packages` answer 410 Gone (moved), not a permission refusal.
   - Only when the bill itself needs explaining, sample jobs per workflow and reconcile the result against the bill.
   - In Git Bash, write the endpoint without a leading `/`: `gh api /orgs/...` turns into `C:/Program Files/Git/orgs/...`.

**Why item 8** (w1188, 2026-10-13). Ben was told GitHub cost "200 a month last month because of CI runners".

- The billing API answered in 4 calls: net $0 in September and October.
- The $200 was ff-factory's gross for October 1–13 ($202.52), all discounted because ff-factory is public.
- Sampled job timings, about 155 REST calls in all, only explained which workflows made that gross figure.

**Why.** On 2026-10-13, around 00:04 UTC, two surveys spent the account's budget together: w1173 read 1,963 job
logs, and w1175 read 4,349 runs of FinalFactory's main.yml with their jobs and then started on job logs. CI and
every other worker's `gh` stalled until the reset (lothsahn, w1187: "Please add it to both lessons, yes"). w1175
finished its census on the cheap path, about 60 REST calls for the run list and about 130 GraphQL queries for jobs,
steps and failed test names. w1185 (lothsahn: "Why was github rate limiting us? What was causing the majority of the
github calls?") counted the two hours. The first ran out at 00:03:56, mostly on w1167's (CI placement) `minutes.py`:
one REST jobs call per run for 1,887 runs, 8 threads, five runs of the script, about 4,600 calls in 33 minutes (job
calls measured, the rest estimated). The second ran out by 00:12:58, mostly on w1173's `survey2.sh` with `xargs -P 8`
(1,963 job logs, each a `gh run view --job --log`). w1175's 4,349 runs went through GraphQL, which has its own budget;
it made only about 12 REST log calls before the refusals. A refusal's request id ends in the call's Unix time in hex
(`…:6ACD756C` = 00:03:56 UTC). The game repo's recipe for its own CI: FinalFactory `Documentation/CI-Runs.md`,
"Reading weeks of CI history without spending the account's API budget".

## A crash inside a GPU driver is not "nothing to fix" until four checks are done (w956, 2026-10-13)

**The rule.** When a player's crash has no game or Unity frame on its stack, only a GPU driver's
(`nvgpucomp64.dll`, `nvwgf2umx.dll`, `amdxx64.dll`, `igd10iumd64.dll`, ...), "driver bug, nothing to
fix" is a guess. Do these four checks before a NOT-A-BUG verdict, and put each one in the verdict
with its source:

1. **Date the driver** from the vendor's own release notes. NVIDIA's file version `32.0.15.9186` is
   GeForce `591.86`, and the notes are at
   `https://us.download.nvidia.com/Windows/<v>/<v>-win11-win10-release-notes.pdf` (read them with
   `pdftotext`). Note how many releases behind current it is, and what those notes list as open and
   fixed.
2. **Read the CPU from the dump.** The minidump's SystemInfo stream (stream 7) holds the CPU:
   ProcessorLevel is the family, the high byte of ProcessorRevision is the model, and it also gives
   the logical processor count. MiscInfo (stream 15) gives the nominal MHz.
   - Intel family 6 model 0xB7 or 0xBF is Raptor Lake (13th/14th gen). Its Vmin-shift instability
     is fixed by microcode 0x12B, and it is a known source of `nvgpucomp64.dll` crashes in many
     games.
   - A twenty-line Python reader is enough for this. No debugger is needed.
3. **Find the game step that fed the driver** at that moment, from the log lines before
   `Crash!!!`: a warm-up, a load, a first draw. Measure how long that step runs in a built player.
4. **Ask whether the game can keep that player booting** without taking anything from other
   players. Examples: a guard that turns the step off after a crash during it, a narrower step, a
   per-driver opt-out. Turning it off for everyone is not the answer. If no lever exists, say why.

**Why (w956, 2026-10-13).** FFBox diagnosed report 20261011T004500Z-crash-f5bded0557 as NOT-A-BUG,
"NVIDIA's display driver crashed inside its own shader compiler", and the request was closed. Ben
reopened it: "yea look into the driver isssue more since it was from 2026". He did not accept
"driver, nothing to fix". The checks found:
- The driver was 591.86 from January 27, 2026. Its notes list no compiler crash, open or fixed,
  and 617.42 (October 6, 2026) was current.
- The dump's CPU was family 6 model 0xB7, 32 threads, nominal 3200 MHz: an i9-class Raptor Lake.
- The game's boot `PipelineWarmup` was compiling its first Direct3D 11 list, a 6.9 s step measured on
  lothdesktop.
- The lever was a guard: after a crash during the warm-up, the next launches of that game version
  on that graphics device skip it (game PR #1658).

**How to apply.** A crash triage that ends in "driver" carries the four lines above: driver date
and position, CPU, the game step and its length, and the lever or why there is none. A reviewer who
sees a NOT-A-BUG crash verdict without them sends it back.

## "How it always worked": read today's handler before you change it (w2097, 2026-10-25)

**The rule.** When a person describes a behaviour as how it has always worked ("always have been unless this regressed",
"this is how it used to work"), read the code that handles it on master today, and the same code a year back
(`git show <old sha>:<file>`), before you change anything. Change only the part the code does not already do, and quote
the line of theirs that names it.

**Why.** w2097 (stacked windows) asked about the E key and selecting a building. Ben: "selecting something has always
closed the inventory/craft panel if it was open, and pressing E to open the inventory/craft panel would close any UI
panels that were open". I read the second half as "one E press closes the windows and opens Inventory" and changed
`UiController.HandleInventoryTogglePressed`. Ben's next answer: "Okay, this isn't quite right ... if windows are open of any
kind, E will close them. If no windows are open, E will open the inventory and craft main panels." That is exactly
master's `if (!CloseAllPanels()) { ... _playerMainPanel.SetActive(!IsInventoryPanelOpen); }`, unchanged since 2020. The
change was reverted and the stills went round Ben once more. Only the first half (a selection closes Inventory) was
missing from the code.

**How to apply.** Per behaviour the person names: the handler's `file:line` on master, what it does in one line, and
whether it already matches their words. Bring a person a question only where the code and their words differ, and
show them the current behaviour first.
