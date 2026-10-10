---
name: settle-your-own-guesses
description: "The evidence gate is self-enforced. An agent settles a guess by research or measurement and then proceeds; the person is asked only for money values, for what the rules reserve for them, and for a fork research could not settle. A CI job that died at its timeout or with every test green is read before it is re-run."
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
