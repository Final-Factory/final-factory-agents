# Unity's command-line -testFilter is a slow regex filter: never pass it hundreds of classes

**When:** w1180, 2026-10-13, the game repo's merge gate (a pull request's `Test in editmode` runs only the classes
the change touches, `.github/scripts/merge-gate-tests.py`).

`unity-editor -runTests -testFilter X` hands X to the test framework as regex group names (com.unity.test-framework
`CommandLineTest/SettingsBuilder.cs`: `groupNames = testFilters`, split on `;`); a dotted class name never takes the
exact-match shortcut (`RuntimeTestRunnerFilter.OptimizedGroupFilter`). 18d49ec4 made it one anchored alternation
(`scripts/test_select.py` `cli_filter`): 485 s against 1,130 s for a `;` list of 311 classes. Even one regex costs a
lot, and it grows with the class count. Measured in CI job logs, from `Running tests for ExecutionSettings` to
`Executing IPrebuildSetup` (the first test):

| filter | wait before the first test | tests | test time | whole job |
|---|---|---|---|---|
| none (the whole suite) | 34 s | ~12,000 | ~13 min | ~18 min |
| ~50 classes (#1603, #1614) | 4-4.3 min | 286 | 2.5-3.5 min | 11-13 min |
| 206 classes (#1602) | 9 min | 1,463 | 12.5 min | 25.9 min |
| 918 classes (#1585) | 19 min | 8,045 | 26 min | 49.8 min |

Every filtered test also runs several times slower than unfiltered (about 0.7 s a test against 0.065 s).

**The fix, measured (w1180, 2026-10-18, m3, batchmode, back to back):** the game repo's
`Assets/Editor/MergeGateTestRunner.cs` (`-executeMethod MergeGateTestRunner.Run -ffTestNames <file> -ffTestResults
<xml>`) builds a `Filter` with `testNames`. The same 200 classes, 1,905 tests: 504 s wall through `-testFilter`, 55 s
through the runner, editor start included. The merge gate uses it since PR #1888, and the 80-class cap is gone.

**Never name a `[SetUpFixture]`.** It is the parent node of every test in its namespace, so naming it selects them all,
in `testNames` and in the regex alike. `scripts/test_select.py` named `Tests.SourceScanCacheRunScope` (the `Tests`
namespace's) for any change near source scans: a 725-class selection ran all 14,124 tests, 6,567 once it was dropped
(`test_select.SETUP_FIXTURE`, PR #1888). A selection that runs "the whole suite" though it names a fraction of the
classes has one in it.

**How to apply:**
- A CI or batchmode run of a selection: use `MergeGateTestRunner` (exact names), never `-runTests -testFilter` with
  more than a few classes; never assume a regex-filtered run is cheaper than the whole suite.
- The MCP bridge's `run_tests` with `test_names` (exact names, the fast path) does not have this cost: 4.0 s against
  16.6 s for one class by regex `group_names` (w546). An `-executeMethod` runner that builds a `Filter` with `testNames`
  is the way to get that on the command line.
- The `cdp.cloud.unity3d.com` "Curl error 6" lines in a CI log are the editor's analytics heartbeat failing on the
  fenced container. Usually harmless, but sometimes the editor goes silent for minutes and the silence ends on one
  (w2236, 2026-10-26, run 40249280445 on ffghr-loth2400-3: no output 00:38:28 to 00:42:00 while
  `CircuitSaveRoundTripTests.ACircuit_RidesTheSave_WithItsTargetRemapped`, 0.02-0.08 s in other runs, ran 209.8 s
  and hit its 180 s timeout, and its sibling tests took 0.05 s; the same log had silent gaps of 235, 100 and 82 s, each
  ending on that line). Whether the DNS lookup causes the stall or only logs first after it is not proven. So a lone
  `Timeout value of 180000 ms was exceeded` on a fast test, with a long silent gap in the job log, is a runner stall:
  check that test's duration in the base's and master's latest full runs, then `gh run rerun <id> --failed` (the
  re-run passed) before touching code, and never raise the timeout. Find the gaps by diffing consecutive log
  timestamps (a gap over 20 s).
