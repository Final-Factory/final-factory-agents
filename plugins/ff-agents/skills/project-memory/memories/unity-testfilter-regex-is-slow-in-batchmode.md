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

**How to apply:**
- A CI or batchmode run of a selection: cap the class count (the gate's `MAX_CLASSES = 80`, PR #1614), or run the
  whole suite unfiltered when the selection is large; never assume a filtered run is cheaper.
- The MCP bridge's `run_tests` with `test_names` (exact names, the fast path) does not have this cost: 4.0 s against
  16.6 s for one class by regex `group_names` (w546). An `-executeMethod` runner that builds a `Filter` with `testNames`
  is the way to get that on the command line.
- The `cdp.cloud.unity3d.com` "Curl error 6" lines in a CI log are the editor's analytics heartbeat failing every
  60 s on the fenced container; they block nothing.
