---
name: verify-simulation-at-a-slow-hosts-frame-rate
description: "A simulation, timing or system-placement change is verified at both frame cadences: a frame without a heartbeat must change no simulation state, and the multiplayer check holds the host near one frame per heartbeat against fast clients. A same-speed pair cannot see a frame-order fork. The pair is any two free machines; a cross-OS pair only when the change can differ by platform. A CI test asserts no wall-clock ratio and waits on real I/O in seconds, not frames. A test that asserts on timing is its own test tagged [Category(\"Performance\")], which no CI runs; a functional test never carries the tag, and a mis-tagged or mixed test is fixed where it is met."
date: 2026-10-04
---

# Verify simulation at a slow host's frame rate

**Rule.** Simulation runs only on the heartbeat (the `FFFixed*` groups and the ops the ordered drain
applies); everything that runs per rendered frame is presentation and writes nothing the simulation
reads, derived caches included. Every claim that a simulation, timing or system-placement change is
deterministic rests on two checks:

1. a test that runs one rendered frame **without** a heartbeat through the real group placement and
   asserts that no simulation state changed, then one **with** a heartbeat (pattern:
   `Assets/Tests/Multiplayer/PerFrameSimulationWriteTest.cs`);
2. a multiplayer run where the host is held near one frame per heartbeat (about 20 fps at 16 UPS)
   against 60 fps clients, and the reverse.

A pair of peers at the same speed cannot show the fork: it only appears when one peer applies an op
and the next heartbeat in the same frame and the other does not.

**Why.** 2026-10-03 (w342, w356). A Steam Deck host at about 20 fps forked alone a few heartbeats
after an Unbuild (0.50.0.71, session e8242f4c). The deletion chain and the item recount ran every
frame in `FFControllerLateGroup`: on a 60 fps client they ran between the op and the next fixed
step, on the host after it. Every nightly pair ran its peers uncapped on one PC, so no scenario
could see it. The audit that followed found five more per-frame writers of simulation state (heat
production, a ship's `LinearMotion.Disable`, the networked item cache, a star's slots, a component
added to every transform entity), a host-only request leg advancing a saved counter, and a
`DisabledKnnWanderSystem` that threw in the editor and ran in release players. The census counted
77k presentation entities through that every-entity component.

**How to apply.**

- Placing or moving a system: name its group in the PR. A per-frame system must pass
  `PerFrameSystemCensusTest` with a reason, and a `[Save]` write from per-frame code is a move or a
  listed reason, never silent.
- Moving a per-frame writer to the tick: put it OrderLast in its own controller group's fixed
  subgroup, so a heartbeat frame runs it where it ran before.
- Host-only code (a request leg, a publisher) writes no simulation state; the op's apply does, on
  every peer.
- The multiplayer check names its frame rates. Slow host with the nightly harness:
  `ffnightly.py run ... --peer-arg host=-ffFeelProbe --peer-arg host=-ffFeelFps --peer-arg host=20
  --peer-arg host=-ffFeelVsync --peer-arg host=0` (the feel probe holds `Application.targetFrameRate`);
  the reverse puts the same flags on the clients.
- [The merge checklist](../checklists/merge.md) carries the line for `Kind: simulation`.

## A new system runs in a test before the first in-game run (w809, 2026-10-09)

**Rule.** For each new or changed `ISystem`/`SystemBase`: a test creates the world, makes an entity the system
matches, and calls the system's update at least once (`World.CreateFFISystemForTesting<T>()`,
`UpdateAndComplete`), then asserts what it wrote. A system tested only through its logic helpers is untested.
Presentation systems count: they run on the first frame of every world.

**Why (w809, 2026-10-09).** `RailgunAnimationSystem`'s job took the structure's pose as an `in LocalTransform`
parameter and wrote its parts' poses through a writeable `ComponentLookup<LocalTransform>`: Unity's job safety throws
an aliasing error the first frame a gun exists. Forty-odd railgun tests and the full fast suite (9,381 tests) were green
because none scheduled that system; loading a new golden fixture in PlayMode threw it. The same request's first
player build failed Burst (BC1016) on `RailgunSystem.OnCreate`, which carried its own `[BurstCompile]` and built a
`FixedString64Bytes` from a string, because `BurstManagedStringGuardTest` skipped lifecycle methods by name (fixed: it
now scans an `OnCreate` that has its own attribute).

**How to apply.** Write the system's test before the first in-game run. Make it red first on the broken shape (restore
the old code, run, see the exception, restore the fix): w809's two animation tests failed with the aliasing error on the
old job and pass on the new. A first built player or PlayMode load of a new feature is the second check, not the first.

## A CI test does not gate on the clock (w857, 2026-10-10)


**Rule.** A test CI runs is verified at the host's speed, not yours.

1. A test the editmode job runs never asserts a wall-clock ratio or a time limit on shared
   hardware. Put the timing in its own test tagged `[Category("Performance")]` and `[Explicit]`
   ([below](#a-timing-test-is-tagged-performance-and-checks-nothing-else-w1690-2026-10-21), w1690), and in
   the CI test assert what the speed-up is made of, which is deterministic: the job type, the batch
   count, the result.
2. A `[UnityTest]` that waits for real I/O or a worker thread counts **seconds** (a `Stopwatch`
   against the command's own deadline), never frames. A headless editor runs frames in
   microseconds, an interactive one throttles them to about 10 ms, so a frame budget passes on
   your editor and fails in CI.
3. A Burst option change in a test (`EnableBurstCompileSynchronously`, safety checks off) is a cold
   compile in CI, minutes long. Measure the test's duration before you add one.

**Why.** w857 (2026-10-10): `InterpolationRestoreCostTest` failed 14 of the 73 editmode runs
measured since it landed, its best-pass ratio ranging 33-92 % (median 59 %) against a 70 % bar,
and its cold Burst compile took a median 422 s (max 536 s against its own 600 s limit) of a 14
minute job. It was the re-run behind #1365, #1357 and #1369, about 30 minutes each.
`AuditWriteCommandTest` waited 600 frames for a file write: a local `-batchmode` run spent them in
under 33 ms and failed 2 of 2, the interactive editor passed.

**How to measure which tests flake** (all of this is retained, none of it needs a local run):

- Runs and attempts: `gh api repos/Final-Factory/FinalFactory/actions/workflows/53376253/runs`,
  then `actions/runs/<id>/attempts/<n>/jobs`. A test is a flake when attempt 1 failed it and a
  later attempt of the same run passed.
- Failed test names: `gh api --allow-escape-sequences repos/.../actions/jobs/<job id>/logs`, the
  `FAIL: <name>` lines and the message under each.
- Per-test duration and `TestContext.WriteLine` output for every run since July: artifact
  `Test results for editmode` (`actions/artifacts?name=...`, `/zip`). A timing test's own printed
  numbers are in there.
- CI-speed frames locally: stop your editor, then
  `unity-slot run -- Unity -batchmode -nographics -projectPath . -runTests -testPlatform EditMode -testFilter <name> -testResults <xml>`.
- A failure that repeats across unrelated branches inside one day and not afterwards is a broken
  master, not a flake; one that passes on re-run is.

## A timing test is tagged Performance and checks nothing else (w1690, 2026-10-21)

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

## A determinism pair is any two free machines; a cross-OS pair only when the change can differ by platform (w1692, 2026-10-21)

**Rule** (lothsahn, w1692).

1. A simulation change's multiplayer determinism check runs two players on whatever machines are free, on any OS: two
   Windows players, a Linux pair, or a Mac host with a Windows client. Do not pin the check to a machine or an OS the change does not need. A Mac
   multiplayer client is still refused (`scripts/nightly/player_slots.py`, w1306), so a Mac takes part only as the host.
2. A cross-OS pair (a Mac host against a Windows or Linux client: arm64 against x64, two compilers, two OSes) is needed
   only when the change can behave differently across CPU architectures, compilers or OSes:
   - floating-point or math-library use in the simulation (`float`, `Mathf`, `math.sin`, a library's own math);
   - Burst or IL2CPP codegen-sensitive code (a new Burst job shape, intrinsics, float modes);
   - platform-specific APIs, or file and IO paths;
   - the desync hash or how it is captured;
   - a desync reported only across OSes.
3. The report and the PR's Evidence name the pair that ran and say in one line why the change did or did not need a
   cross-OS pair. A brief asks for a cross-OS pair only for one of the cases in rule 2, and names it.

**Why.** lothsahn, 2026-10-21: "We should only schedule a cross os determinism check if truly needed. There's only one
m3 and m5 is often offline". For w1689 (a sleep-system guard with no floating-point math) he chose "Use two Windows
players for w1689's multiplayer check", then corrected the default: "Not windows by default, any OS.  Being particular
about a machine or OS limits the fleet we can use." A cross-OS pair waits for the one Mac that can host, so a needless
one stalls the request; a same-OS pair still catches every order, frame-cadence and per-peer fork (rule 2 of the section
at the top: hold the host near 20 fps whatever the OS).

**How to apply.** Before you ask for the run, read the diff against the list in rule 2. None applies: ask for "two
players, any free machines" and write "no cross-OS pair: <why>" in the Evidence row. One applies: ask for a Mac host
and a Windows or Linux client, name the case, and say which machines you need and for how long.

## A pair run is filed only on a commit that compiles (w2125, 2026-10-25)

**Rule.** Before `request_pair` (a two-machine pair run), the commit its legs run must have compiled: a green
`Test in editmode` CI run at that head, or a `refresh_unity` at that head in your own editor with no `error CS` in its
log. With no editor free, wait for the PR's CI on that head (`blocked_on` with `ci:`) and file the pair run after it.

**Why.** w2125 (the nightly check of #2489 and #2400) pushed a new EditMode test file while every Unity slot on
lothdesktop was taken, so it was never compiled. The pair run, w2131, was filed on that head, f2e31d387c, straight
away. The file lacked `using FFCore.Extensions;` (`CS0103: The name 'Ecs' does not exist`), and the PR's own CI run
40185213438 on that commit was already red with the same error. The host leg's `build_player.sh` stopped in its prepare
pass, the whole pair was spent, and a fresh pair run had to be filed after the fix. A test file reaches the player build
too: `build_player.sh` compiles every assembly, test assemblies included.
