---
name: read-why-a-ci-job-died-before-rerunning
description: "A CI job cancelled at its timeout, or failed with every test green, is read before it is re-run: a job with no log at all lost its runner; a job with its log names the test that hung; 'coverage file is empty' is a node child ended mid-exit. A re-run alone hides the cause and costs the next PR the same twenty minutes."
date: 2026-10-10
---

# Read why a CI job died before re-running it

**Rule.** Before re-running a job that was cancelled at its timeout or failed with every test green, find out which
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
