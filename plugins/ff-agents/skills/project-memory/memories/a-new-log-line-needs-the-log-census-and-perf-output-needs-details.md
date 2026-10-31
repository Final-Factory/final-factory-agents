# A new log line needs the hot-path log census; a Performance test's output needs include_details

**Request:** w2622 (the ship dispatch registry rewrite, for lothsahn), 2026-10-31, m3 slot1.

## A system that gains a `Debug.Log*` line: run `HotPathLogCensusTest`

The game repo's `Assets/Tests/Logging/HotPathLogCensusTest.cs` lists every log call in a hot-path system with its
reason, and fails on a new one. w2622 step 2 added a warning for the ownerless-ship repair. The local run covered only
the dispatch test classes, so it missed the census failure. It surfaced afterwards and needed a second commit
(`8a7bfd98a9`, "the ownerless-ship repair's warning gets its hot-path log census entry").

**How to apply:** when a diff adds a `Debug.Log`, `LogWarning` or `LogError` line to any FFSystems system, add
`Tests.Logging.HotPathLogCensusTest` to your local `run_tests` names. Running the full
`python scripts/test_select.py` selection also covers it. Add the census entry in the same commit.

## A Performance test's numbers come back only with `include_details`

A `[Category("Performance")]` test writes its numbers with `TestContext.WriteLine`. MCP `get_test_job` returns that
output only with `include_details: true`, in `results[].output`; the default answer has the pass count alone. The
shared TestResults.xml is not the place to read it (the game repo's CLAUDE.md). w2622 read every bench row that way:
`run_tests` with the exact test name, then `get_test_job` with `include_details: true, wait_timeout: 60`.
