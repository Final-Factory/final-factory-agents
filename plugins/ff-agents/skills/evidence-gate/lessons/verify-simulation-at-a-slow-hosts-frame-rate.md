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

## A single-machine MP scenario never runs on a Mac (w3697, 2026-11-08)

**Rule.** `ffnightly.py` starts every peer of an `MP-*` scenario on the computer it runs on, host and client side by
side, unless a pair lab (`scripts/nightly/lab.pair-*.json`) or the pair relay (`scripts/nightly/pair_relay.py`) spreads
them over two computers. The game repo's `scripts/nightly/player_slots.py` `require_mac_client_ok` refuses any
multiplayer client on a Mac (w665's Metal GPU page fault hangs the whole Mac), so such a run cannot run on a Mac at all,
not even as the "host" leg of a pair. Only `FF_MAC_GPU_HANG_OK=<request>` lifts the guard, for a w665 repro whose Mac's
person agreed to unlock it afterwards.

**Why.** w3669, the pair run for PR #3433 (w3642's MP-W1587-gatling-tiers scenario fix), said "The scenario runs both
peers, host and client, on one computer, so every leg works on its own", and FF Factory still put leg 1 on m5, since its
pair rule was "a Mac only as the host" (w2282). The m5 leg built a Mac player of 72d10b50d7 (about 10 minutes) and all 3
runs ended `env` in about 20 s at the guard (2026-11-08 18:00 UTC): a whole leg, a build and a worker spent for no result.
Ben: after a wasted run, the harness learns.

**How to apply.** A pair run or a brief whose legs each run an MP scenario alone says so ("each leg runs host and client
on its own computer") and asks for Windows or Linux legs only. FF Factory enforces it since w3697: a pair or request whose
words name an `MP-*` scenario takes no Mac (`shared/capacity.ts` `macRefusedScenario`; `start_agent` refuses one too),
unless it is cross-OS, its words name a pair lab or `pair_relay`, or they carry `FF_MAC_GPU_HANG_OK=<request>`. A real
Mac-host pair (m5 hosts, BEAST joins through `lab.pair-m5-beast.json`) names its lab in the brief so a Mac may host it.

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

**Again in w3436 (2026-11-07), on a fail-before push.** The RED push of PR #3363 (its fixes switched off, to show the
new tests fail) carried a new `GuardianMountSaveTest.cs` that had never compiled: the same missing
`using FFCore.Extensions;` (`CS0103 'Ecs'`). CI run 42406242143 failed in compile, not in the tests, and proved nothing;
the RED had to be pushed again. The rule covers every push whose point is a test result (a RED push, a pair run, a
merge): compile the new test file first, by `refresh_unity` and a `run_tests` of `test_select.py`'s selection that
names it. A new test file that uses `Ecs.*` needs `using FFCore.Extensions;`.

## A pair run is filed only on a player build and a dry run that pass (w2963, 2026-11-04)

**Rule.** An editor compile is not enough for a pair run of a simulation change. Before `request_pair`, at the head
the legs will run:

1. **Build a player yourself** (`scripts/nightly/build_player.sh <project> <sha> win <cache>`, under `unity-slot run`;
   about 10 minutes on BEAST with `FF_BUILD_BURST_X64_TARGETS=16`, measured) and grep its log for `error CS` and `BC1`
   lines. Burst AOT compiles every `[BurstCompile]` method only in a player build; the editor runs a Burst `OnCreate`
   managed, so EditMode passes code a player build refuses.
2. **Pass the scenario's host-only dry run on that player** (`ffnightly.py run --player <dir> --scenario <id>-dry`,
   made by the pair script's `--dry`), with the value asserts the pair will check (exact raw values, counts), not
   only "no error".

**Why.** w2963 (Ancient Dragon stage 2, PR #3123). Its first pair run, w3003, never ran: both legs' player builds of
c894f941 failed Burst BC1028 at `DragonDamageForwardSystem.cs:84`, a `params EntityQuery[]` `RequireAnyForUpdate`
in a `[BurstCompile] OnCreate`, while every EditMode test passed. w3003's dry run on a probe fix then found two more
bugs EditMode had missed: a kill on a flat map's tile with no biome entry dropped no Mover (moverBoxes 0), and the
pool lost 4,000 raw of 24,000 on an engaged heartbeat's rescale. After a local player build and dry run passed, the
rerun w3005 passed the first time (2,396 heartbeats, no divergence). w3004 added `BurstManagedArrayGuardTest` for the
BC1028 class; the build and the dry run catch the rest.

## A client leg reaches the host from its own machine first (w2259, 2026-10-26)

**Rule.** An address that works from one machine is a claim about that machine only. Before a client leg builds or
joins a host on another computer:

1. **Probe from the client's machine**, not from yours or the host's: `python scripts/nightly/reach.py @<host machine>`
   (game repo; the machine's addresses are in `scripts/nightly/lab_hosts.json`), or `reach.py <addr> <addr>` with the
   addresses the host leg posted. It ends `PICKED <ip>` (join that one) or `UNREACHABLE: ... tried ...`.
2. **Prefer the Tailscale address.** Every machine on the tailnet routes to a 100.x address; a 10.0.0.x or 192.168.x
   address answers only on its own LAN. Keep LAN as the fallback for a client whose Tailscale is stuck (w1982).
3. **On no answer, stop and say so**: name every address tried, tell the other legs, and let another machine take the
   leg. Never let the game's join timeout be the probe.
4. **Name machines, not IPs, in configs and skills**: `"hostAddress": "@m3"` in a lab config, `m3` (MagicDNS) in a
   script default. One file holds the addresses, so a changed one is fixed once.

**Why.** w2252 (2026-10-26, the Leech target-scan pair for PR #2590): `lab.m3.json`, `lab.pair-m3-beast.json` and
`lab.pair-m3-rosetta-beast.json` hardcoded the m3's LAN address 10.0.0.110, as did the determinism-audit skill's
`CLIENT_HOST` default. It had always worked because the only client was BEAST, on the same LAN. When the client leg
moved to LothDesktop, every ping to 10.0.0.110 was lost and the first join timed out after 150 s; the m3's Tailscale
address 100.104.235.48 answered and the join worked. w1976 (2026-10-24) was the same miss from the other side: a client
built its player for 10 min before learning its own Tailscale was stuck.

**How to apply.** The merge checklist's pair-run line asks for the probe's `PICKED` line from each client machine.
ffnightly runs the same pick before every remote join (`ScenarioRun.host_address`, w2259), and
`scripts/tests/test_nightly_reach.py` fails on a lab config that hardcodes a non-loopback address.

## A pair leg's player dies to another worker's timed run, and an old client rejoins the next host (w2407, 2026-10-27)

**Rule.** A pair-run leg launches its player with `player_slots.py launch --bench-wait <s>`, and reads
`[QuitSave] ApplicationQuit: not saving (AutomationProcess)` in its player log, with no quit of its own, as "FF Factory
closed it for another worker's timed run": that scenario is void, and the leg tells its partner at once with
`message_pair`. When the computer keeps taking exclusive timed runs back to back, the redo goes to a leg on a computer
that is not, rather than a second retry there. Between scenarios a client is ended as soon as its result is taken:
a client whose host went away keeps reconnecting to the same address and joins the next scenario's fresh host.

**Why.** w2407 (2026-10-27, the w2383 Connection Lost pair: m5 host, LothDesktop client, b293e240a9): the relay-suspend
scenario's client was closed by the bench turn at 14:10Z for w2401's timed run, before the host was suspended at
14:10:49Z, so the host lost a relay session with no client in it; the redo's client waited for the lock until 14:30Z,
started, and was closed again before it joined, for w2355's timed run at 14:34Z. The scenario never got a live client
on that computer. In the same run the transport-failure scenario's client showed "Connection lost — reconnecting (2/4)"
and on its third attempt joined the host's next, fresh session (`[Reconnect] ReconnectRestored attempts=3`), polluting it.

**How to apply.** The merge checklist's pair-run lines ask for it; a leg's report names any scenario voided this way.

## A pair run is sized to its slowest required event, not the brief's minimum (w2570, 2026-10-29)

**Rule.** Before a pair run starts, work out from the brief's measured rates the heartbeat at which each required event
lands (each flip, each crossing, each state the pass criteria name), and run the leg after the join to the latest of
them plus a margin, never only to the stated heartbeat minimum. Dump the state the criteria read at intervals (not only
at the end), so a run that dies early still shows which events happened, and take the end-of-run dump on every leg.

**Why.** w2570 run 4 (the w2551 range-circuit pair on PR #2825, eec773da; biscuit host, BEAST client) ran 8,997
heartbeats after the join with 0 desyncs in 1,124 checks, past the brief's 8,000 minimum, and saw the battery latch go off
at 80 %. It could not see the latch come back on at 60 %: the drain is about 20 % x 25 s x 16 UPS = 8,000 heartbeats
after the off-flip, so the on-flip needed about 9,000 to 11,000. The host session then stopped on a usage limit and its
player quit with it, so no end-of-run dump was taken on either side. The run had to be redone (w2582) at 14,400.

**How to apply.** The merge checklist's pair-run lines ask for it: the brief or scenario states the heartbeat each
required event is expected at and the run length chosen from it.

## A census diff names a cause only from lines aligned at one heartbeat (w3436, 2026-11-07)

**Rule.** To find what a join save left out, diff the `CensusAtSample(hb N, ...)` lines of both peers' halves for
the same heartbeat. A `CensusDetail` line is a live dump at each peer's own `currentHeartbeat`, so two of them differ by
time alone. A host report that says `sampleHeartbeat=unavailable (no retained sample for the verdict heartbeat)` or
`aligned capture missed: a session reset (a recovery) replaced this world` has no aligned census. A diff against it
gives leads, labelled guesses, never the cause. Get an aligned pair first (a census dump at the join on both peers, or
a host that keeps its sample), then name the component.

**Why.** w3436 checked whether PR #3363 fixed BaseSurviving's join desync (r141). The paired host report of the
loopback run held the client's census at hb 8 but only the host's live census at hb 268. Bats looked like the cause:
the same 2401 bats in different tag signatures. But both tags are `[Save]`, and 260 heartbeats of fighting explain the
split as well. What could be said was what the census proved: BaseSurviving has no live Guardian in either census, so the
Guardian fix cannot reach it. That went up as a follow-up that asks for an aligned census first.


## A runtime-added [Save] buffer is kept empty, or says why it need not be (w3850, 2026-11-09)

### The rule

When code adds a `[Save]` `IBufferElementData` to an entity at runtime (`AddBuffer<T>`, `AddComponent<T>`, an ECB add, a
`typeof(T)` in a type set) and that entity's prefab does not bake `T`, either list `T` in
`ColumnarWorldCapture.KeepsEmptyBuffer` (`Assets/Scripts/Serialization/Columnar/ColumnarWorldCapture.cs`) or give it a
verdict with a reason in the `SafeToDropEmpty` allow-list of `Assets/Tests/Serialization/EmptySaveBufferGuardTest.cs`.
The fast-suite guard fails the PR otherwise. `EmptySaveBufferJoinCensusTest` then proves the join census for each kept
type with no extra work.

### Why

Both save writers (columnar and legacy `MarshallingSystem`) drop an empty buffer unless `KeepsEmptyBuffer` lists it,
and the loader rebuilds each entity from its prefab. The entity census (`DeterminismStateFingerprint.CensusHash`)
counts component types by presence. So a joiner whose copy lost an empty runtime-added buffer has a different census:
desync at heartbeat 8, RecoveryFailed, client kicked. Players found it four times (HandCraftHeldItem, w3816 / game PR
#3485; PendingRotation; IncomingShieldHit; GuardianSpine). The guard written for w3850 (game PR #3498, 2026-11-09)
found nine more on its first run: PersonalLogisticsRequest, DysonShellRecord, CircuitCalculation, CircuitSetItem,
HaulerStopCircuit, HaulerStopCircuitCondition, HaulerStopHeading, PastedStationStop and
PastedStationStopCircuitCondition.

Keeping every empty buffer by default was rejected: it changes every save and drops the "zero-length buffers are treated
as absent, so prefab defaults survive" contract that load repairs rely on.

### How to apply

- A new runtime `AddBuffer` of a `[Save]` type: ask "can it be empty at a heartbeat, on an entity whose prefab lacks
  it?" Yes or unsure: add the `KeepsEmptyBuffer` line. Provably no (baked on every prefab that gets it, re-added before
  the census, or the component is removed when it empties): an allow-list entry naming the file:line that proves it.
- The guard is a source scan: a buffer added through a generic type parameter is invisible to it, so check that case by
  hand.
- Docs: game repo `Documentation/SaveFormat.md`, the empty-buffer section.
