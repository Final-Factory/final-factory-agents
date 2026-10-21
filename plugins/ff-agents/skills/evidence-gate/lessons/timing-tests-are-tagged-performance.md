---
name: timing-tests-are-tagged-performance
description: "A game test that asserts on timing carries [Category(\"Performance\")] and checks nothing functional; a functional test never carries it. Performance tests run in no CI, only locally against a same-machine baseline. A worker that meets a mis-tagged or mixed test fixes the tagging."
date: 2026-10-21
---

# A timing test is tagged Performance and checks nothing else

**Rule** (lothsahn, 2026-10-21, w1690).

1. **Agents may write performance tests.** Any game test that asserts on timing (milliseconds, frame time,
   throughput, a speed ceiling or a speed ratio) carries `[Category("Performance")]`. Add
   `[Explicit("a performance measurement: no CI run executes it; run it by name")]` beside it, as the game repo's
   performance tests do, so a whole-assembly run in an editor skips it too.
2. **A performance test is its own test.** No test checks both behaviour and timing. A functional test never
   carries the Performance category: every game CI lane leaves the category out (`MergeGateTestRunner` for the PR
   gate and the master batch, `-testCategory '!^Performance$'` for the push, release and nightly runs, FFBox's
   `scripts/ffverify.sh`), so a functional test tagged Performance silently stops guarding anything.
3. **Performance tests run in no CI.** Run them locally by name and compare against a baseline measured on the same
   machine (master against your branch, back to back), never against the test's ceiling. Dedicated performance
   hardware that runs only these tests may come later; it does not exist today. Never loosen a timing threshold to
   make CI pass: a timing test that fails in CI is mis-tagged, so tag it.
4. **Fix the tagging where you meet it.** A worker that runs into a timing test without the tag, a functional test
   with it, or a test that checks both, fixes it in the same change or in its own small PR. Split a mixed test in
   two: the functional assertions stay untagged and keep running in CI, and the timing assertion moves to a tagged
   test. No audit is needed beyond the tests you touch or run.

What counts as timing: a `Stopwatch`, `realtimeSinceStartup`, `ProfilerRecorder`, `Measure.*`, `DateTime.Now` or
an allocation byte count compared against an upper bound that depends on how fast the machine is. What does not: an
exact count (zero allocations, a number of trips for a fixed seed), and a hang guard or a deadline seconds wide that
only catches a test that would otherwise never end. Those are functional and stay untagged.

**Why.** lothsahn, 2026-10-21: "We should NOT be running performance tests on the regression tests for the build
server." "The build server is 4x slower than beast." Then (w1690): "Tell the agents they can still write performance
tests but they should all be flagged performance if they check timings. The performance test should be separated
from any functional tests, which must not be flagged. I'll look into setting up dedicated infra for performance tests
that will run only the performance tests. ... Should a worker run into a performance test that's not tagged (or vice
versa) it should fix the tagging". `CircuitEvaluationBenchmark`'s 2.0 ms ceiling read 2.17 and 2.98 ms on a loaded
build server and failed two release runs in a row, which kept 1.0.0.5 and 1.0.0.6 off Steam; beast reads 0.11 ms.
w1687 (PR #2142) took every timing test out of CI and split the mixed ones (`WaypointsTest`,
`LogisticsBotStressTest`).

**How to apply.**

- Writing a test: decide first whether it checks behaviour or speed. Behaviour: no clock in an assertion, no tag.
  Speed: its own test, tagged, logging its numbers, with the run-by-name line in its doc comment.
- Touching or running a test: read its asserts. A clock compared against a bound with no tag, or the tag on a test
  whose asserts are all functional, or both kinds in one test: fix it now (rule 4).
- The game repo's `PerformanceTestCensusTest` fails a test file that reads a clock and asserts an upper bound
  without the tag (or a reasoned entry in its `Reviewed` list). It cannot see a functional test wrongly tagged, or a
  mixed test inside a tagged file: those are yours to catch.
- Running one: `run_tests` with `assembly_names` and the exact `test_names`, master then your branch, on the same
  machine. Full text in the game repo: `Documentation/CI-Runs.md`, "Performance tests are local-only".
