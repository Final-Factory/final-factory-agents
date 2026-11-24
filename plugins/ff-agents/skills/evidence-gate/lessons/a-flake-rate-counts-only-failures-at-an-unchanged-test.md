---
name: a-flake-rate-counts-only-failures-at-an-unchanged-test
description: "Before fixing a test the test-results ledger ranks as flaky, read where each failure came from: local runs on a feature branch while that test, or the editor, was mid-change are no flake. Diff the failing run's and the next passing run's runs.changes, count CI runs apart, and prove a verdict with 50+ repeats on master."
date: 2026-11-24
---

# A flake rate counts only failures at an unchanged test

**Rule.** A rank in `test_history false_positives byRate` is a lead, not a diagnosis. Before you hunt a cause, read each
failure's run (source, branch, machine) and split the counts by source. A failure counts as a flake only when the test
and the game code were the same in the failing run and in the pass after it, and the editor was healthy. Then prove the
verdict by running the tests 50 or more times on current master with Burst on.

**Why (w5454, 2026-11-24).** lothsahn asked to "Fix all tests with a greater than 1% flake rate". The mobile-station share
was 11 cases ranked at 1.3% to 5%. All 69 of their failures were local runs on in-progress feature branches (w4972,
w5000, w5277, w5371, w5373); the 356 CI runs (pr-gate 314, release 38, other 4) had none. Two causes covered every "fp":

1. **The test was being edited.** The ledger keys a run on HEAD, so uncommitted edits look like "no change". Its
   `runs.changes` column is a JSON map of each dirty file to its blob. Between the failing run and the next pass, only
   `DockingGlideTest.cs` or `HoldFormationTakeOffWaitTest.cs` changed, and the game code's blobs matched. Three failing
   runs gave the same stop position to the micrometre (`float2(-134.578f, 1785.588f)`): a deterministic miss in a test
   being written, not chance.
2. **A broken editor.** Burst NREs in `HaulerFormationPaceSystem` hit every Hold Formation test, untouched ones too. That
   worker restarted the editor and the same files passed (transcript 837a6bd6, 05:09 to 05:16 UTC).

Master then passed 75 of 75 repeats (825 case runs) on BEAST: nothing to fix.

**How to apply.**

- Split by source first: `SELECT r.source, count(*), sum(res.outcome='fail') FROM tests t JOIN results res ON
  res.test_id=t.id JOIN runs r ON r.id=res.run_id WHERE t.class IN (...) GROUP BY 1` (filter on `t.class`, or the
  10 s limit stops it).
- For each fp, find the next passing run of that test on the same branch and diff the two runs' `changes`:
  `json_each((SELECT changes FROM runs WHERE id=<fail>))` LEFT JOINed with the pass's on `key`, keeping rows whose
  `value` differs or is missing. A test file in that diff means the test was being edited.
- No file difference: read that worker's transcript at that time (`search_transcripts` on the exception) for a restart,
  a stale Burst compile or a reload, before you call it a flake.
- Repeat with one script (`unity-bridge.py run-tests --tests A,B,...` in a loop, counting `passed N of N`). Count a
  dropped-bridge iteration (`bridge closed the connection`, then `tests_running`) as not run, never as a pass.
