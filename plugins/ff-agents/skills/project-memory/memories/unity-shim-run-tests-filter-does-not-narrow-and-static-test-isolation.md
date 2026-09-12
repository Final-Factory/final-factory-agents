---
name: unity-shim-run-tests-filter-does-not-narrow-and-static-test-isolation
description: "`unity command … run_tests filter=X filter_type=testName` ran the WHOLE EditMode set (4036) and Temp/pipeline_test_status.json can be STALE from an earlier run — read the shim's own JSON (result.Summary + result.Results[].Status), never grep 'Total'; a second run in one domain showed 9 failures the fresh domain did not (static HeartbeatSystem._lastAppliedSessionResetEpoch + 8 TearDown 'SteamId cannot be null' log exceptions) — clear test-facing statics in SetUp and judge a suite from a fresh-domain run."
---

# The shim's test-name filter does not narrow, the status file can be stale, and statics leak between runs (2026-09-12, 069 relay #8)

- **Filtering.** Two runs through `~/.local/bin/unity` with `--filter <TestClass> --filter_type testName`
  reported `Total: 4036` — the entire `FFEditorTests` set, not the class (069 plan 16:45 PROGRESS block).
  Assume a test-name filter does NOT narrow; use `--filter FFEditorTests --filter_type assembly` and find your
  cases by `FullName` in the results.
- **Read the shim's JSON, not the status file.** `Temp/pipeline_test_status.json` can carry a PREVIOUS run's
  counts while the new run is in flight or finished. The shim's own output is authoritative:
  `result.Summary.{Total,Passed,Failed,Skipped}` and `result.Results[] = {FullName, Status, Duration, Message,
  StackTrace}` (shape: `…/240c7805…/scratchpad/tests-fast-1.json`). Parse `Results[].Status`; never grep
  `"Total"`. (Corrects [[unity-cli-mpdev-build-recipe]], which pointed at the status file.)
- **Statics survive between runs in one domain.** `HeartbeatSystem._lastAppliedSessionResetEpoch`
  (`HeartbeatSystem.cs:63`, read by `IsSessionResetApplied` `:65`) kept the epoch a previous run applied, so
  `HeartbeatCatchUpTest.NonServedPeer…` "nothing applied yet" passed in a fresh domain and failed on the SECOND
  run in the same domain — together with 8 TearDown `SteamId cannot be null` log exceptions in unrelated
  classes. Fix `2306524df`: `HeartbeatSystem.ClearAppliedSessionResetForTests()` (`:75-77`) from the test's
  `[SetUp]` (`HeartbeatCatchUpTest.cs:30-33`). Rule: any static a test asserts on gets a `SetUp` clear, and a
  suite verdict comes from ONE fresh-domain run (the recompile before it gives you that domain for free).
- Related: [[unity-cli-mpdev-build-recipe]], [[feedback-verify-compile-from-editor-log]].
