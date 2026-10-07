---
name: editor-ops
description: Final Factory Unity editor operations via the MCP bridge — pinning the right editor instance, compile verification after code changes (the stale-assembly and .meta false-green traps), running the EditMode test suites, editor readiness/recovery when the bridge is down or the editor hangs, the Unity CLI recovery channel, long-background-run monitoring, and editor memory capture. Use BEFORE any task that needs the live editor - running tests, verifying a compile, entering play mode, recovering a stuck editor or bridge, or monitoring a long build/audit run.
---


**Multi-machine orchestration is the default:** read and apply
[Ben's all-machines requirement](../project-memory/memories/feedback-prove-over-live-networked-machines.md).
Assign the available fleet real work, run live built-player acceptance across those machines,
and collect each job's result. Local tests and local subagents do not substitute for remote coverage.
# Editor operations (MCP bridge, verification, recovery)

**Standing authorization:** Ben has authorized launching, driving, screenshotting, testing, and recovering Final Factory on his machines during development. Do not ask again for app use or routine playtest steps. Use existing project-specific tools, bounded calls, and autonomous recovery; platform permissions remain independently enforced. Read [the authorization and uninterrupted-run rule](../project-memory/memories/drive-interactive-verification.md) before handing any routine step back to Ben.


This is the full operational detail behind the game repo CLAUDE.md's Build & Test kernel, kept
here so it loads on demand. The rules below are binding, not advisory.

## Runtime translation

The workflows in this shared skill apply to both Claude Code and Codex. Use the native tools
that the current runtime exposes; do not invoke one agent runtime's CLI from the other.

- **Claude Code roles keep their declared Claude models.** In particular, `game-driver` and the
  other plugin roles remain Claude roles; do not rewrite them to use Codex models.
- **Codex routing:** the main driver is Astra; designed implementation goes to Sol at medium
  effort; focused lookups go to scout on Luna at low effort; broad exploration goes to Explore
  on Terra at low effort; mechanical edits go to mech-executor on Terra at medium effort; review
  angles go to reviewer on Terra at high effort. These are runtime adapters, not changes to the
  Claude role definitions. For the live topology and worker CLI recipe, read
  [`references/codex-fleet.md`](references/codex-fleet.md).
- **Unity MCP works in both runtimes.** Inspect the current tool and resource inventory for the
  Unity MCP server, read `mcpforunity://instances`, match the instance by its absolute project
  path, and pin it before any editor action. A different tool prefix or an initially hidden tool
  does not mean Codex lacks Unity MCP; discover the available tools before declaring the bridge
  unavailable.

The standalone `unity` CLI is for a remote editor, targeted recovery, or a runtime where the
Unity MCP tools truly are unavailable after discovery. State which of those reasons applies.
When MCP returns, re-pin the matching project and verify any CLI result through MCP before using
it as the final compile, test, or play-mode verdict.

## The MCP bridge is the primary editor-control channel

All normal editor interaction — entering/exiting play mode, injecting input, loading saves,
querying editor/scene state, compile verification, running tests, capturing screenshots — goes
through the Unity MCP bridge tools (see `Documentation/Unity-MCP-Setup.md` and the
`drive-game` skill). **Do not substitute file-based evidence channels** (trigger files,
editor-log tailing, DLL-mtime watching) on your own initiative: they are slow and error-prone
in many edge cases (e.g. a compile failure never updates the assembly file, so a file-watcher
hangs forever). If the bridge is down or stale, recover the exact editor/bridge yourself using
the workflow below, then return to MCP for authoritative work. The file-trigger flows
documented elsewhere (memory snapshots, the determinism harness) remain limited to their
explicit workflows.

**Visual changes are verified on video, not stills** (Ben, 2026-09-29). Any change to VFX, shaders,
animations, particles, camera feel or other visual presentation gets 60 fps clips, before and after,
from gameplay angles, covering the effect's whole lifetime (`record_clip`). Review them with
`watch_video --mode vfx` against a written description of the intended look, and step through the
frames. The PR links the clips and the review report. Once Ben has approved a look, compare
against that approved clip. Screenshots alone don't count. Recipe: `ff-agents:watch-video`.

## Mechanized preflight — run the script, don't recall the prose

**`scripts/editor-preflight.sh <project-path>`** (game repo) is the executable form of this
skill's recurring editor-readiness traps. Run it BEFORE any task that needs the live editor;
each failure message carries its own diagnosis and fix:

- exit 1 — no editor process owns the project (launch via `scripts/launch-editor.sh`);
- exit 2 — process alive but loopback silent = the NATIVE MODAL class; the message gives the
  `sample`-based diagnosis recipe;
- exit 3 — not idle (compiling / play mode — where compiles are silently ignored);
- exit 5 — Burst disabled or still draining (codegen asymmetry forks the sim, 062).

`scripts/editor-preflight.sh --await-zero <project-path>` is the zero-poll gate before any
relaunch (the `open -n` double-instance trap). The prose sections below remain the
explanation of WHAT the failures mean; the script is how you check.

## Resolve and pin the target instance FIRST

For ANY task that needs the live editor (compile/test confirmation, play mode, screenshots,
scene/state queries), the *very first* action is: read `mcpforunity://instances`, find the
instance whose `path` is under THIS project's working directory, and `set_active_instance` to
pin it. If the resource is empty, stale, or has no matching path, enter the recovery workflow
below. A stray running `Unity.exe` is NOT proof this project's editor is live (Unity Hub,
another copy, a batchmode build, or a stale process all show up too); only the pinned MCP
instance's `path` counts.

Multiple Unity editors are routinely connected at once (e.g. FinalFactory, FinalFactory2,
FinalFactory2_clone_0, FinalFactory3, FinalFactory4, …). Do NOT hardcode a project name — the
matching instance differs per working copy. An unpinned run can execute against — and report
results from — the *wrong* project. Alternatively pass `unity_instance` per call.

### "No Unity Editor instances found" mid-session — transient, re-pin by PORT

Discovery drops a perfectly healthy editor for a fraction of a second around domain reloads and
test-run boundaries, and the failure then sticks for up to 5 s. Measured on Windows /
FinalFactory2, 2026-09-12, mcpforunityserver 10.0.0 + com.coplaydev.unity-mcp v10.0.0.

Recovery, in this order:

1. Wait ~2 s and retry the same call. Every drop window measured was sub-second; the error
   outlives it only because the empty result is cached (`unity_connection.py:487`, 5 s TTL).
2. Still failing → `set_active_instance` with the editor's PORT NUMBER (usually 6400; confirm
   with `Get-NetTCPConnection -State Listen -OwningProcess <unity pid>`). The port form calls
   `discover_all_instances(force_refresh=True)`, which busts that cache. That is why re-pinning
   works — it is NOT bypassing a staleness filter.
3. Expect to repeat step 2 after EVERY domain reload and test run in a long session.

Why: discovery requires `~/.unity-mcp/unity-mcp-status-<sha1(dataPath)[:8]>.json`
(`port_discovery.py:237`) — a port file alone never registers an instance. Three transient
windows make that file or its socket unusable, and in each the resolver hard-fails on the empty
list (`unity_connection.py:544`) BEFORE it looks at your pinned instance, so a pin cannot save
the call:

| Window | Measured | Covered by the 60 s `reloading` grace? |
|---|---|---|
| `Stop()` deletes the status file; the `reloading` heartbeat is written after | 6 ms | No — no file left to grace |
| Listener aborts connections while tearing down, before `reloading` is set | one isolated sample, <500 ms | No — `reloading` still false |
| Listener down during the reload itself | ~8 s | **Yes** — this one works correctly |

**Do NOT chase `PortDiscovery.CONNECT_TIMEOUT`** (`port_discovery.py:32`, 0.3 s). It looks like
the culprit and is not. Across 809 samples spanning a full `FFEditorTests` run and two reloads,
every probe while the listener was up answered in **1–26 ms, p50 2 ms** — the ping is served
inline on the listener's async path (`StdioBridgeHost.cs:584-591`), never queued to the main
thread, so a saturated editor does not slow it. Every failure was a REFUSED or ABORTED
connection, which no timeout value can fix. Nor is there a knob: that timeout, the 60 s grace,
the 5 s cache and the 0.5 s heartbeat cadence are all hardcoded literals — no env var (30
`UNITY_MCP_*` checked), no config file, no EditorPrefs key (63 checked) — and upstream `beta`
10.0.1-beta.3 is byte-identical. A real fix means patching the Unity C# package, which is not
ours to modify.

Two things that look like this bug and are not:

- `Timeout receiving Unity response` / `Command TCS timed out` in Editor.log is main-thread
  starvation. Real commands queue and drain only in `ProcessCommands` on
  `EditorApplication.update` (`StdioBridgeHost.cs:357`), so a busy editor stops servicing them
  while still answering pings. Wait for idle; re-pinning changes nothing.
- `editor/state` reporting `blocking_reasons: ["stale_status"]` under load is NORMAL. The
  heartbeat writer sits on that same update tick and went **56.5 s** stale during one EditMode
  suite. Harmless while the port answers — but that is only 3.5 s from the 60 s cliff above, so
  a slower suite can turn a clean reload into a real drop.

At session start, `instance_count: 0` usually means the editor is still BOOTING, not that the
bridge is broken: the host does not start until project load completes, and no status file
exists before that (`Stop()` deletes it on clean quit, so between sessions there is none).
FinalFactory2 measured a 208 s boot — 191 s of it AssetDatabase refresh — after a large merge.
Confirm the process and whether it is listening before starting any recovery.

## Cross-machine runs and implementor legs contend for the same pinned editor

A cross-machine determinism run and an `implementor`/`build-verifier` leg on the same machine
fight over the ONE pinned editor: a leg's `refresh_unity` during a paired play session breaks
the run, and a run's preflight fails on an editor that is mid-compile from a leg's edit.
Sequence them — run first, leg after, or the reverse — never overlap, and put the "wait until
`play_mode.is_playing` is false" rule in every leg brief so a delegated agent doesn't step on a
live run it can't see.

A Windows GUI player started through SSH can run in Session 0 and stall at DX11 window setup even
though its process exists. Before recovery, identify the exact executable, PID, Windows session,
and owned log. Preserve that attempt, stop only the positively identified player, and launch the
task-owned executable in the already logged-in desktop session through a uniquely named scoped
task. Clean up only that task, its automation config, and its player. Never stop Steam, a user's
game, Unity Hub, or another checkout's editor. The full cross-machine evidence gate is in
[project memory](../project-memory/memories/cross-machine-built-player-gameplay-acceptance.md).

Also relevant when a leg runs from a worktree: `EnterWorktree` branches from `origin/MASTER` in
this repo, not `develop` (`git reset --hard origin/develop` first — see
[project memory](../project-memory/memories/enterworktree-cuts-from-master-not-develop.md)), and
a worktree has no `Library/`, so compile verification still happens in the MAIN editor after an
ff-merge, not in the worktree.

## Editor readiness and recovery are the agent's job

**Unity crashes and freezes constantly, and agents have full authority to restart their own
editor whenever it's hung, crashed, frozen, stuck in a bad state (domain-reload loop,
unresponsive bridge, wedged play mode, stuck compile), or otherwise misbehaving — no need to
ask Ben first** (Ben, 2026-09-24, emphatic;
[[feedback-restart-unity-on-your-own-authority]] carries the full rule, the startup-dialog
quick reference, and the ~5-minute-unresponsive heuristic). In an ffsb sandbox, restart via the
sandbox's own `mcp__sandbox__unity` tool (`restart`, `force` if needed) rather than killing
processes by hand. Never ask the user to babysit imports, compiles, bridge recovery, or editor
restarts. Verify, recover, and monitor readiness yourself:

1. **Bridge up?** Read `mcpforunity://instances`. Non-empty → pin the instance and go.
2. **Editor busy importing/compiling?** Watch through the bridge, don't ask: poll the
   `mcpforunity://editor/state` resource (`activity.phase`, `compilation.is_compiling`,
   `assets.is_updating`) at a modest cadence until idle. Note the state snapshot can go
   stale while the main thread is saturated (`staleness.is_stale`) — pair it with a
   process-CPU check to distinguish "working hard" from "hung" before declaring either.
3. **Bridge down, stale, or editor hung? Recover it.** Keep the user informed, but do not hand
   them the recovery work. First resolve the exact checkout through `--project-path`, the MCP
   instance descriptor, or a validated Unity process command line. Use the targeted `unity` CLI
   status/editor-status probes and the `[UnityMcpStdioAutoStart]` startup diagnostic to classify
   the failure. Clear stuck MCP/test state or restore stdio transport when possible. If the exact
   editor remains nonresponsive, stop and restart only that validated project-owned Unity process,
   using the Unity version in `ProjectSettings/ProjectVersion.txt`; never kill by a broad Unity
   name/pattern and never touch Unity Hub or another checkout. Poll `mcpforunity://instances`, pin
   the restored matching path, wait for idle, and resume the interrupted work. Escalate to Ben only
   after targeted recovery has genuinely failed or an external prerequisite (licensing, OS dialog,
   missing installation) requires human action.

Known traps, with signature, diagnosis and recovery, in [references/recovery.md](references/recovery.md).
Open it when the editor or bridge misbehaves:

- `busy: compiling` forever = the editor is stuck in PLAY MODE
- NUnit `TestCaseSource` is enumerated at DISCOVERY, not at run
- A hung BOOT is usually a native modal — relaunching reproduces it
- A compile error present at BOOT lands in native Safe Mode — no automation channel can click it
- A stalled RUNNING editor (Windows): system + editor modals, and FindWindow lies
- The scene-modified modal on macOS: signature, recovery, and the prevention that beats both
- A long-uptime Steam client can wedge play-mode entry (~26h uptime)
- A fresh editor boot with no scene looks wedged, not hung
- A failed batch build leaves `Temp/UnityLockfile`: the next build says the project is open
- An ffsb sandbox shared by two sessions: `switch_branch` refuses, and a commit without switching

## Running tests

Run tests through the MCP bridge with the instance pinned: start a run with `run_tests` and
poll `get_test_job` for results. **After a change, run the tests it touches, not the whole fast
suite** (lothsahn, 2026-10-06, w546): `python scripts/test_select.py` in the game repo reads the
branch's diff against `origin/develop` (plus uncommitted files) and prints the `run_tests`
arguments: `assembly_names ["FFEditorTests"]` and `test_names`, the exact test class names.
CI runs the whole suite on every pull request, so anything the selection leaves out is caught
there. For #1137's change the selection ran in 75 s against 376 s for the full fast suite
(measured, lothdesktop).

- Pass `test_names`, never regex `group_names`. One class through a regex took the job 16.6 s
  against 4.0 s by exact name, and regex runs held the main thread for minutes (measured).
- Give `run_tests` an `init_timeout` of 120000. A call that answers "Timeout receiving Unity
  response" may still have queued the run: poll `get_test_job`, or wait for the editor log's
  "Restored Interaction Mode after test run", before asking again, or the runs stack up.
- Run the full fast suite (`FFEditorTests`) when the selector prints FULL SUITE (the test
  framework, asmdefs, `Packages/`, `ProjectSettings/`, `Assets/Resources/` configs, or a
  selection above 60% of the suite's time) or when someone asks for it. Pass both
  `FFEditorTests` and `FFEditorTestsSlow` (or all EditMode assemblies) only when all tests are
  explicitly requested; run slow tests only if asked.

Verify the tests you ran pass before considering work complete. **Confirm Burst is enabled and
idle before starting any run** — see the next subsection.

**Check which `run_tests` implementation the current route exposes before calling a suite
"fast."** Unity Pipeline's command uses only case-insensitive substring `filter`/
`filter_type`; it ignores `assembly_names`, and an assembly filter for `FFEditorTests` also
matches `FFEditorTestsSlow`. For an exact remote fast suite, use project-scoped CLI `eval_file`
to call public `MCPForUnity.Editor.Tools.RunTests.HandleCommand` with `mode: "EditMode"`,
`assemblyNames: new JArray("FFEditorTests")`, and a suitable `initTimeout`, await its result,
then poll `GetTestJob.HandleCommand` by `job_id` with `includeFailedTests: true`. MCPForUnity
passes that exact array to `Filter.assemblyNames`. The full durable recipe is in
[feedback_test_command](../project-memory/memories/feedback_test_command.md); do not edit either
package to work around Pipeline.

- **Editor tests** (fast): `Assets/Tests/` — FFEditorTests
- **Editor tests** (slow): `Assets/TestsSlow/` — FFEditorTestsSlow
- **Play mode tests**: `Assets/Scripts/PlayModeTests/` — FFPlayModeTests

### Before ANY test run: Burst must be ENABLED, and finished compiling

Burst compilation is an editor setting that can be off, and it does not announce itself. Check
it, turn it on if it is off, then wait for its background queue to drain before starting the
run. Both halves are load-bearing:

- **Correctness — the reason this is a rule.** Code that compiles fine as C#/IL can still FAIL
  Burst (`BC1054`, "Unable to resolve type", internal compiler errors). With Burst off, every
  job silently runs managed, so a green suite proves nothing about whether the Burst-compiled
  code builds at all. Same false-green family as the stale-assembly and missing-`.meta` traps
  below, and it hides the exact class of error the shipped build would hit.
- **Runtime.** Managed job execution is roughly an order of magnitude slower. `FFPerformanceTests`
  measures ~13x, uniformly across production `KnnSystem` and benchmark jobs alike (476 s with
  Burst off against ~45–60 s with it on), which blows the test framework's default 180 s
  per-test watchdog (`UnityWorkItem.k_DefaultTimeout`) and reports a timeout failure that has
  nothing to do with the code under test.

Check and enable through `execute_code`:

```csharp
var o = Unity.Burst.BurstCompiler.Options;
var was = o.EnableBurstCompilation;
if (!was) o.EnableBurstCompilation = true;   // == Jobs > Burst > Enable Compilation
return new { was, now = o.EnableBurstCompilation };
```

Enabling it queues a full background compile, and **Burst is asynchronous** — `refresh_unity`
returning, `ready_for_tools`, and `compilation.is_compiling: false` all say nothing about it.
Poll `Unity.Burst.Editor.BurstLoader.BurstProgressId` until the queue is empty, then scan for
`BC`/`error CS` entries; the polling recipe, the `EnableBurstCompileSynchronously` variant for
when a verdict must be airtight, and the `read_console` filter caveat are all in the
`stale-burst-after-merge` project memory. A run started mid-queue measures the managed fallback
and lets Burst errors hide behind it.

If you turned Burst on, say so in your report — it is a persistent editor setting, and the user
may have switched it off deliberately.

**A NEW `[BurstCompile]` entry point needs a forced synchronous compile, not just a green fast
suite.** The editor compiles Burst lazily — an entry point that no test happens to schedule
during a fast-suite run can sit un-compiled indefinitely, so "fast suite green" is not evidence
it Burst-compiles at all. After adding one, force
`Unity.Burst.BurstCompiler.Options.EnableBurstCompileSynchronously = true`, trigger the code
path, and re-grep `Editor.log`/`read_console` for `BC`/Burst errors before trusting it. Note
player BUILDS compile every entry point unconditionally (the editor does not) — a `BC1016` class
error can pass every editor-side check and only surface on an actual build machine.

**Never read `…/AppData/LocalLow/Never Games/finalfactory/TestResults.xml`** (or
`PerformanceTestResults.json`). The Unity Performance Testing package
(`com.unity.test-framework.performance`, a transitive dependency of `com.unity.entities` /
`com.unity.collections` — it cannot be removed) writes that file on *every* test run to a
path derived from `companyName`/`productName`, which is **shared by all FinalFactory
copies**. Whichever copy ran last clobbers it, so it will silently report another project's
results. The MCP job result is the only authoritative source. Trust ONLY the
`run_tests` / `get_test_job` result for the pinned instance.

### ⚠️ Long single-NUnit-test PlayMode jobs: two bridge defects

Jobs shaped like `PlayModeTests.Runner.DeterminismTestRunner.RunDeterminismGate` — ONE NUnit
test that internally loops many scenarios — emit no sub-test `TestStarted`/`TestFinished`
events, and the bridge's test tracking mis-handles that two ways (evidence:
`specs/049-determinism-gate-coverage/plan.md`, legs 1–2):

1. **False stall flag.** `get_test_job` reports `stuck_suspected: true, blocked_reason:
   "editor_unfocused"` for the entire run and never clears it. Not a stop signal for this job
   shape — ground truth is the on-disk `Editor.log` (real heartbeat/testcase advancement).
2. **Destructive premature teardown.** The bridge's `TestRunnerNoThrottle` can conclude the
   run finished and execute end-of-run teardown ("Restored Interaction Mode after test run" +
   `TestResults.xml` write) while the test is still executing — observed mid-corpus,
   destroying Netcode + the DOTS world under the running test; everything downstream NREs
   (`Ecs.GetCachedSingletonQuery`). Signature: `[TestRunnerNoThrottle] Restored Interaction
   Mode` at a non-boundary, then `[Netcode] ShutdownInternal`. Mitigations: keep the editor
   frontmost for the duration (`osascript -e 'tell application "Unity" to activate'`), treat a
   mid-run teardown as the bridge's failure and retry once, and capture verdicts from the
   Editor.log rather than the job result alone (the job result also loses per-scenario detail).

**Probe hygiene while a bridge is attached:** never clear an `EditorApplication.update` probe
with `EditorApplication.update = null` — that wipes the ENTIRE multicast delegate including
the bridge's own polling, silently killing `editor_state`/`execute_code` (a leg had to
recover the editor to get the bridge back). Subscribe with `+=`, keep the reference, remove
with `-=` — or avoid subscribing and diff `editor_state` sequence/time across calls instead.

### ⚠️ EditMode SUITE runs are also focus-throttled — different failure signature

The single-long-test defects above are not the only focus-dependent bridge failure. An
ordinary EditMode SUITE run (many small tests, not one long NUnit test) is also throttled by
an unfocused editor — observed ~2.4s/test unfocused vs ~64s total for the whole suite
focused — and the bridge then **aborts the job with a false `Test job failed to initialize
(tests did not start within timeout)`**, even though the Editor.log shows the tests
demonstrably still completing. The false-init-timeout error text is the TELL for this class — do
not read it as a real initialization/startup problem; it means the run was too slow to finish
inside the bridge's timeout, not that it never started, and it aborts the whole ~15-minute run.
Mitigation: extend the same tool used above — call
`osascript -e 'tell application "Unity" to activate'` before `run_tests`, AND again every ~2
minutes while polling `get_test_job`, not just once at the start.

## Compile verification — a PASSED result does NOT prove your code compiled

The editor will NOT recompile while it is in **play mode** (compilation blocks during play),
and if compilation **fails** it keeps the **last good assembly**. In either case the test run
executes against **stale code** and still reports `PASSED`. So after EVERY code change you
MUST positively confirm the change actually recompiled and is live — do not trust `PASSED`
alone. **Verify through the MCP bridge, not by watching files**:

1. **Ensure the editor is idle in Edit mode first** (no active/auto-started play session —
   e.g. a determinism-audit run). Recompile triggered during play is silently ignored. Check
   the `mcpforunity://editor/state` resource: `play_mode.is_playing` false, `activity.phase`
   idle.
2. **Trigger and await the compile**: call `refresh_unity`, then poll `editor/state` until
   `compilation.is_compiling` is false and `last_domain_reload_after_unix_ms` is NEWER than
   your edit. (A "Connection closed" error from `refresh_unity` usually IS the domain reload —
   poll state, don't retry blindly.)
3. **Check for compile errors**: `read_console` filtered for `error CS`. Zero entries after a
   fresh domain reload = compiled. On failure the console entry contains the exact file/line.
4. Where a **behavioral signal** is available (a new log line, a changed test count, a changed
   result), prefer confirming it too. Identical-as-before behavior after a "fix" usually means
   the old assembly is still running.
5. **Prove the new code path EXECUTES, not just that it compiled.** A fix shipped behind a
   never-matching gate — an ECS query missing a component the live data doesn't have, a
   `RequireForUpdate`, a feature flag — "lands" cleanly (compiles, suite green, review passes)
   while never executing once, and the dead gate also hides downstream bugs (an unassigned
   lookup, a bad job field) until the gate opens. Probe the live world for the fix's EFFECT
   (state it should have changed, a counter, an instrumented sample), and prove the probe can
   go positive before believing its negative. The worked example this rule comes from: a beam
   re-anchor system's query required `WeaponOwner`, which no live beam owner carried, so two
   shipped "fixes" in it had never run — and a second bug, a never-assigned `ComponentLookup`
   that threw on first scheduling, only surfaced once the query was corrected.

**New `.cs` files**: an unimported script is not compiled at all — 0 errors + fresh domain
reload + green tests can all be true while your new file is absent from the build. Confirm the
`.meta` appeared next to it after refresh.

**Burst disabled**: `error CS` clean + green suite covers the C#/IL compile only. If Burst
compilation is off, no `BC` error can even be produced, so nothing here says the Burst path
builds. Enable Burst and let its queue drain before the run — see "Before ANY test run" above.

**Why not file-based checks**: they're slow and error-prone in a lot of edge cases (e.g. a
compile failure in the editor may never update the watched file, hanging the watcher forever).
Recover MCP first. If the runtime truly has no Unity MCP tools, use the explicitly reported CLI
fallback above and verify the result through MCP when a later session exposes it. If neither
channel can produce evidence, report exactly which compile/test proof remains unavailable.

**Deterministic hooks back this ritual** — the game repo's `.claude/settings.json` +
`scripts/hooks/`, with state under `Library/ClaudeHookState/`. What each signal means and how
to clear it:

- **Stop block listing `.cs` files** = those files were edited with no `refresh_unity` since.
  Clear it by running the ritual above (refresh → fresh domain reload → `error CS` check →
  the tests the change touches if behavior changed), or state explicitly why verification isn't needed, then
  finish. It reminds **once per edit** (game repo, w500): a new edit of a file re-arms it.
  Verified another way (a batchmode `-logFile` compile or a player build log with no
  `error CS`, or a green CI run at a commit holding the edits)? Record it once and the files
  clear: `python scripts/hooks/cs-verified.py --how "<what>" --log <log>` or
  `--ci-run <run id> --commit <sha>`. The script checks the evidence and refuses what does not
  hold; never record a check you did not run.
- **Missing-`.meta` warning after a refresh** = the named new `.cs` files were NEVER imported —
  the false-green trap above is live for them; force a reimport / `scope=all` refresh and
  confirm the `.meta` before trusting any result.
- **Crown-jewel warning on an Edit/Write** = the target matches a glob in
  `Documentation/Crown-Jewel-Surfaces.md` — determinism-critical, driver-only edit territory;
  non-blocking, but re-read the tier rules before proceeding.
- Hooks **fail open** (a broken hook exits silently rather than bricking the session), so hook
  silence is a missing signal, not proof of a clean state — the ritual itself stays binding.

**Bridge console caveat** (Windows box): `read_console` reliably returns warnings/errors/
exceptions but generally NOT plain `Debug.Log` entries — never treat "0 log entries" as proof
a log-line marker didn't fire. It also returns from the START of its buffer rather than the
tail, so pass `filterText` to find recent lines instead of asking for the last N. For Log-level
markers, use a state probe via `execute_code` instead; it compiles via Roslyn on Windows as
well as macOS.

This applies to BOTH editors in a paired run — the clone (`../<project root>_clone_0`) has the
same stale-assembly trap (see the `determinism-audit` skill).

## Unity slots: every Unity launch takes one

**Every Unity process on a machine counts toward its editor limit** (`max_unity`), whoever
started it: sandbox editors, the owner's own, `-batchmode` builds and test runs, the clone editor
of a paired run, editors scripts start. AssetImportWorkers, bcl.exe and built players do not
(w469, Lothsahn on 2026-10-05, after LothDesktop hit 63 of 64 GB with one editor and three
batch builds while its limit of 3 counted one; FF Factory `docs/unity-lifecycle.md`, "Unity
slots").

- Your own editor goes through FF Factory's `unity start` (the `unity` tool). It is refused while
  the machine is full, over 85% RAM, or while launches wait ahead of it; the refusal names who
  holds the slots. `wake_me` and try again, or stop an editor you no longer need. Never kill
  another process's Unity to make room.
- **Every other launch waits for its slot.** Use `unity-slot run [--count N] [--label "<what>"] --
  <command>` (on the PATH of every agent an FF Factory daemon runs) or the game repo's `python
  scripts/unity_slot.py run [--count N] -- <command>`. Each waits in the machine's queue, runs the
  command and frees the slot when it ends. `unity-slot status` (or `python scripts/unity_slot.py
  status`) shows who holds and who waits.
- **A run that needs several editors asks for all of them at once** (`--count 2` for a host plus
  clone pair). Never take them one at a time: two runs each holding one would wait for each
  other. The queue refuses a run that would deadlock; when that happens, release what you hold and
  ask again for everything at once.
- The repo's own scripts take their slot themselves: `build_player.sh` (both passes under one),
  the build passes of the build audits, `run_agent_channel_smoke.sh --build`,
  `bench/capture_raw.sh` (game repo `Documentation/Audit-Script-Index.md`, "Unity slots").
  Launches nested inside a run pass straight through.
- An editor you open by hand beside your own (the clone editor of a paired run, via
  `launch-editor.sh`) needs a held slot: `unity-slot acquire --count 1 --label "clone editor"
  --project <clone path>`, then `unity-slot release <id>` once it is closed (`--ttl`, default 120
  min). Without that, the daemon still counts the editor and nothing else starts while the machine
  is over.
- With no slot arbiter on the machine (a daemon from before w469, a machine without FF Factory)
  both commands run at once and say so.

## Long background runs (player builds, paired audits, multi-minute test jobs)

Keep ownership until every run reaches a terminal state; the user must never have to ask for the
verdict. In Claude Code, arm a Monitor that reports phase changes, periodic progress, and every
terminal state. In Codex, use its native wait tool when the job exposes one; otherwise poll in
the active turn with bounded waits of at most 60 seconds. After each wait, inspect both the phase
and terminal signals (`verdict`, `error`/`Exception`, build failure, process exit), report useful
progress, and wait again until completion or a concrete blocker. Do not end the turn merely
because a background command is still running.

A completion notification alone is insufficient for long silent phases. A single phase can take
20 minutes, so provide a progress heartbeat about every three minutes with the current phase and
the underlying log's last meaningful line. Silence must not be able to mean that the process
crashed.

**A timed-out synchronous `execute_code` build may still be running.** A long call that times out
has been seen to leave the build running and produce repeated invocations and completion markers.
Do not assume the timeout cancelled the work. Schedule the build once from an
`EditorApplication.update` callback instead. The callback must remove its own delegate before
starting the build, and task-owned persistent `scheduled` and `started` guards must make a second
submission a no-op. After a timeout, inspect those guards, the existing job state, and the build
output or result marker before deciding what happened.

## Building

**A successful result label is not sufficient.** Accept a native player build only when
`BuildReport.summary.result == Succeeded` **and** `summary.totalErrors == 0`; inspect the
reported C# and Burst diagnostics as well. A guarded completion marker proves only that the
build method returned. Preserve any rejected artifact and its diagnostics, recover the exact
project editor/JIT using the existing ritual when indicated, and rebuild before live testing.
See [the observed false-success build](../project-memory/memories/build-report-success-with-errors.md).

Before transferring or launching a build, also check that its
`StreamingAssets/EntityScenes/` contains the main SubScene's `.entityheader` and
`.0.entities` files (resolve the GUID from `Assets/Scenes/main/EntitySubScene.unity.meta`).
`scene_info.bin` alone is an incomplete package, even with zero build errors and
`CleanBuildCache`. Preserve it; force-reimport the SubScene through the pinned editor and
rebuild into a fresh output, then repeat the file check and a real startup. Never repair a
new player by copying baked scene data from an older build. Give every startup retry a fresh
audit identity, including retries that never loaded a world.

**Run a build from the player slot pool, never where it was built.** Windows Firewall keys its
rules on the exe path, so a player started from a new folder (a sandbox's `Builds/pilot`, a temp
output) stops at the "allow finalfactory.exe?" prompt. `python scripts/nightly/player_slots.py
launch [--detach] <exe|folder|.app> -- <player args>` mirrors it into an allowed slot path and runs
it there (On a worker-root install (LothDesktop since w576) each sandbox slotK has its own two player folders, `players/slotK-0` and `slotK-1`: `launch` picks them from the sandbox it runs in, and `--peer 1` puts a same-build client in `slotK-1` (project-memory `feedback-built-players-run-from-the-slot-pool`).); bash scripts source `scripts/nightly/player_launch.sh` and use
`"${FF_LAUNCH[@]}" "$PLAYER" -- …`. The audit, feel and bench scripts and `ffnightly.py` already
do (project-memory `feedback-built-players-run-from-the-slot-pool`).

Release builds and Steam uploads are NOT made from an editor: they go through CI on the ffbox build
server, via the `ci-release` skill. Never make a release with `Build > Build and Upload All` or
steamcmd. ffbox sets a develop release live on `development` and a master release on
`pre-release`; `mp-beta-deploy` is the last-resort M5 fallback, only when ffbox CI is actually down and only with
Ben's OK.

## Capturing editor memory

Use the MCP bridge — call `execute_code` to run a resident-memory breakdown that sums
`Profiler.GetRuntimeMemorySizeLong` per loaded-object category (Textures/Meshes/AudioClips/…)
plus engine totals (GfxDriver, Mono heap); `manage_profiler` covers profiler-marker captures.
(`Assets/Editor/MemorySnapshotTrigger.cs` still implements exactly this breakdown — mirror
its logic in the `execute_code` snippet.) It measures *editor-resident* memory (includes
editor-only objects), so it is for **relative before/after comparison in the same editor
state**, not absolute player numbers. This lets Claude measure memory changes itself instead
of asking the user to capture snapshots.
