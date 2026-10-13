---
name: settle-your-own-guesses
description: "The evidence gate is self-enforced. An agent settles a guess by research or measurement and then proceeds; the person is asked only for money values, for what the rules reserve for them, and for a fork research could not settle. A CI job that died at its timeout or with every test green is read before it is re-run. A bulk read of GitHub history takes the cheap path and stays well inside the account's shared API budget. A crash with only GPU-driver frames is not \"nothing to fix\" until the driver is dated, the CPU read from the dump, the game step that fed it measured and a guard looked for."
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
