---
name: editor-ops
description: Final Factory Unity editor operations via the MCP bridge — pinning the right editor instance, compile verification after code changes (the stale-assembly and .meta false-green traps), running the EditMode test suites, editor readiness/recovery when the bridge is down or the editor hangs, the Unity CLI fallback channel, long-background-run monitoring, and editor memory capture. Use BEFORE any task that needs the live editor - running tests, verifying a compile, entering play mode, recovering a stuck editor or bridge, or monitoring a long build/audit run.
---

# Editor operations (MCP bridge, verification, recovery)

This is the full operational detail behind the game repo CLAUDE.md's Build & Test kernel
(moved here by feature 061 so it loads on demand). The rules below are binding, not advisory.

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

## Mechanized preflight — run the script, don't recall the prose

**`scripts/editor-preflight.sh <project-path>`** (game repo, 2026-08-16 harness review G9) is
the executable form of this skill's recurring editor-readiness traps. Run it BEFORE any task
that needs the live editor; each failure message carries its own diagnosis and fix:

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

## Editor readiness and recovery are the agent's job

Never ask the user to babysit imports, compiles, bridge recovery, or editor restarts. Verify,
recover, and monitor readiness yourself:

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

### `busy: compiling` forever = the editor is stuck in PLAY MODE (2026-08-15, feature 064)

`run_tests` kept returning `{"error":"busy","reason":"compiling"}` on every retry, while
`~/.unity-mcp/unity-mcp-status-<hash>.json` said `"reason":"ready"` with a fresh heartbeat and
`refresh_unity` timed out waiting for readiness. The editor was in play mode, which blocks script
compilation indefinitely, so it was permanently "about to compile" and never would be.

Diagnose and clear it in two calls — do not restart the editor for this:

```csharp
// 1. execute_code — the MCP status file will NOT tell you this
return "isPlaying=" + UnityEditor.EditorApplication.isPlaying
     + " isCompiling=" + UnityEditor.EditorApplication.isCompiling;
// 2. execute_code
UnityEditor.EditorApplication.isPlaying = false;
```

`isPlaying=True isCompiling=True` that never resolves is the signature. Note `execute_code` keeps
working while play mode blocks compiles, so the bridge looks healthy — and a stray
`.ff-local-automation.json` is a common cause but not the only one (there was none in this case).

### NUnit `TestCaseSource` is enumerated at DISCOVERY, not at run

A parameterized test whose source reads the filesystem (a saves folder, an artifact directory)
builds its case list when the assembly is discovered. Changing those files mid-session does not
change the case list — the next run replays the stale cases. **Force a domain reload
(`UnityEditor.EditorUtility.RequestScriptReload()`) after changing anything a `TestCaseSource`
reads**, or you will "verify" against the previous state and believe the result.

Corollary from the same session: **`[Explicit]` does not stop such a test from running.** Invoking
`run_tests(assembly_names: [...])` executes explicit tests — confirmed by a stack trace showing the
body had entered. If a test is expensive enough that firing it unintentionally hurts (feature 064's
corpus sweep: ~18 min of blocked editor), gate it on something real — an environment variable
checked *before* it touches the filesystem. Treat `[Explicit]` as a label, not a guard.

### A hung BOOT is usually a native modal — relaunching reproduces it

(2026-08-11, M3 Pro; cost ~10 min and two pointless relaunches before it was diagnosed.) An
editor that never finishes booting is more often blocked on a modal dialog than crashed or
stuck importing. Symptom triad — all three together:

- `Editor.log` frozen at ~2 KB, last line `[Licensing::Module] Licensing Background thread has
  ended` (nothing after the licensing handshake);
- the process at **0% CPU**, state `SN`, **RSS stuck near 150 MB** (a real booting FinalFactory
  editor climbs past 1 GB within seconds);
- `mcpforunity://instances` reports `instance_count: 0` while `ps` shows a live Unity with the
  correct `-projectPath`.

**Diagnose it with `sample`, not the log** — the log will never say anything, because the modal
blocks before the next write:

```sh
sample <pid> 2 -f /tmp/unity_sample.txt && grep -A 40 "Call graph" /tmp/unity_sample.txt
```

A main-thread graph ending in `Application::InitializeProject() ->
Application::HandleDanglingSceneBackups() -> GetDialogResponse ->
EditorDialog::DisplayDecisionDialogNative -> ShowAlertDialog -> [NSAlert runModal]` means Unity
is waiting on the **"recover backed-up scene?"** decision dialog. An earlier editor CRASH left
`Temp/__Backupscenes/0.backup` behind, and EVERY subsequent launch re-pops it — so the standard
kill-and-relaunch recovery *reproduces* the hang instead of fixing it.

Fix: kill the editor (precondition-check its `-projectPath` first), delete
`Temp/__Backupscenes` and any stale `Temp/UnityLockfile`, then relaunch. Boot proceeds normally
and the bridge registers.

**PREVENTION IS NOW MANDATORY (2026-08-16, Ben: top priority — this modal kept recurring): on
macOS, launch automation editors ONLY through the game repo's `scripts/launch-editor.sh`**
(landed `d9a3dced0`). Before launching it clears all three boot-wedge hazards —
`Temp/__Backupscenes`, stale `Temp/UnityLockfile`, `Library/LastSceneManagerSetup.txt` (the
no-auto-scene guard) — resolves the editor version from `ProjectSettings/ProjectVersion.txt`,
and refuses to double-launch onto a project that already has a live editor (the `open -n`
trap). Any unclean editor death (crash, SIGKILL) re-arms the modal for the NEXT boot, and the
modal is native and pre-boot — no MCP/unity-cli channel exists yet to dismiss it — so ad-hoc
`nohup Unity -projectPath …` launches WILL eventually wedge. After the script launches, open
the boot scene explicitly via `eval_file` as usual. Automation editors never hold deliberate
unsaved scene work, so discarding the backups is always correct on this path.

⚠️ Deleting that backup discards unsaved SCENE edits from the crashed session — check
`git status -- '*.unity'` first. After an agent-driven play session there is normally nothing
of value there. Note `osascript`/System Events cannot enumerate the dialog (no assistive
access), so `sample` is the tool that works headlessly.

### A stalled RUNNING editor (Windows): system + editor modals, and FindWindow lies

(2026-08-11, BEAST, 049 toggles-join harness leg; cost ~40 min.) Same symptom family as the
boot modal but on ALREADY-RUNNING editors: process `Responding=True` at ~0% CPU, the editor
log fills with MCP `Command TCS timed out (N consecutive)`, a requested script compilation
never starts, and `run-tests-fast.trigger` is never picked up — the editor UPDATE LOOP is
stalled, not the process. Two modal classes confirmed live, STACKED (dismissing the first
revealed the second):

1. **Windows Security firewall prompt** for a launched player build (mode-2 gate runs spawn
   one per run's fresh build path). It is a UWP window — `user32 FindWindow(null, "Windows
   Security")` returns NOTHING while it is on screen, so "no dialog found" proves nothing.
   Only a screenshot shows it. Dismiss with a DPI-aware click on **Cancel** (= keep the
   default block; localhost pairing is unaffected — whole corpus runs pass with it blocked).
2. **Unity "open scene(s) have been modified externally — Reload/Ignore"** — appears when a
   `git pull` changes an open scene on disk under a running editor (clones sharing `Assets`
   by symlink get it too). **Reload** is correct unless the editor holds deliberate unsaved
   scene work.

Recovery recipe: DPI-aware screenshot FIRST (`SetProcessDPIAware` before `CopyFromScreen`,
and capture+click in ONE process — the DPI trap is per-process and bidirectional), click the
top modal, screenshot again — modals stack, so repeat until the desktop is clean. The editor
loop resumes instantly; re-trigger whatever was queued. Both editors on a box can be stalled
by ONE system modal at the same time.

### The scene-modified modal on macOS: signature, recovery, and the prevention that beats both

(2026-08-14, M5+M3, 062 order-instrument cycles; the modal wedged three editors across two
days and twice masqueraded as "slow compile".) The macOS signature of a RUNNING editor blocked
by the **"open scene(s) have been modified externally — Reload/Ignore"** dialog: process alive
at ~0% CPU in state `SN`, `Editor.log` still receiving worker-thread writes — specifically the
pipeline server logging `Main thread operation timed out after 60000ms` on every request — and
BOTH control channels (MCP bridge `execute_code` and `unity-cli`) timing out. When things
"take a long time", suspect this FIRST, before diagnosing compiles: look at the window (Orca
computer-use; accessibility granted on M5 2026-08-14) and click **Reload** (correct unless the
editor holds deliberate unsaved scene work). If UI automation is unavailable, kill the
path-verified editor process and use the prevention recipe below on relaunch.

**Prevention — the standard harness bring-up, which makes the dialog structurally impossible:**

1. Quit editors BEFORE any git operation that changes `.unity` files (merge, checkout, rebase).
   Clean quit from inside: `EditorApplication.delayCall += () => EditorApplication.Exit(0)` via
   `execute_code` (needs `safety_checks=false`) or `unity-cli eval_file`.
2. Delete `Library/LastSceneManagerSetup.txt` before relaunching — the editor then auto-opens
   NO scene, so no open scene exists for a disk change to invalidate.
3. After the editor reports ready, open the boot scene explicitly from current disk state:
   `EditorSceneManager.OpenScene("Assets/Scenes/main.unity")` via `eval_file`.

Two adjacent traps from the same incident:

- **`open -n` double-instance:** launching over ssh with `open -n … -projectPath X` while an
  editor already runs on X silently spawns a SECOND instance that wedges on the
  "project already open" / "another Unity instance is running" dialog and poisons probes for
  both. The race that keeps causing it: relaunching right after QUEUEING a quit (delayCall
  Exit or SIGTERM) without waiting for the old process to die. HARD RULE: after any quit/kill,
  POLL `ps -axo pid,command | grep -c "[M]acOS/Unity -projectPath <path>$"` until it reads
  ZERO, and only then launch — a fixed sleep is not a substitute (bit three times 2026-08-15).
  (And path-verify EVERY remote kill — `MacOS/Unity` also matches the licensing client.)
- **Post-checkout stale assemblies look "ready":** after a `git checkout <older-rev>` under an
  editor whose Library was built at tip, `editor_status` reports ready and types shared by both
  revisions resolve — proving nothing. Verify the loaded assemblies with a symbol that exists
  in ONLY one of the two revisions (e.g. a type the newer rev added must be ABSENT after an
  older-rev checkout), then force `recompile` if wrong.

(Added 2026-07-21 on the Windows box; Mac shim added 2026-07-22.) The project carries
`com.unity.pipeline` (exp), which runs a loopback HTTP server in the editor (ports 7800–7849,
auto-starts, survives domain reloads) that a standalone `unity` CLI talks to with NO MCP
involvement. On Windows this is `%LOCALAPPDATA%\Unity\bin\unity.exe`; **on macOS there is no
official binary, but the game repo ships a working shim at `scripts/unity-cli.sh`** (plain
bash, built from the package's own documented HTTP protocol —
`Library/PackageCache/com.unity.pipeline@*/Documentation~/connectivity.md` in any checkout —
port descriptor file + bearer token + JSON POSTs to `/api/exec`). It's not on PATH by
default — symlink/copy it once per machine, e.g.
`ln -s "$(pwd)/scripts/unity-cli.sh" ~/.local/bin/unity && chmod +x ~/.local/bin/unity`,
then invoke it as `unity` like the Windows CLI.

It is genuinely useful beyond the down-bridge case: `unity command --project-path <path>
recompile` + `recompile_status` returns structured `{status,failed,errors}` JSON, a cleaner
compile-verification signal than grepping `Editor.log`; `eval_file file=<path.cs>` runs
arbitrary C# on any project path directly, handy for probing two paired editors without
swapping MCP's `set_active_instance`. When the MCP bridge is down this is also the sanctioned
*diagnostic and recovery* channel — it does NOT replace MCP as the authoritative normal-work
channel; it lets you answer "is the editor alive / compiling / in play mode?" without the
bridge: `unity status`, `unity command editor_status`, `unity command eval 'return <expr>;'`
(full statement with `return`+`;`; on Windows PS 5.1 eats embedded double quotes — keep code
quote-free or use a file via `eval_file`; the Mac shim has no such quoting trap since it isn't
PowerShell, but `eval_file` is still cleaner for anything nontrivial).

⚠️ **Always target with `--project-path <abs path>`** — it is the ONLY working selector
(routes correctly with multiple servers, hard-fails if that project isn't connected). On
Windows, `--instance host:port` is IGNORED by command routing in 1.0.0-beta.2 (verified live
2026-07-21, two servers up): with exactly one connected server your command runs there no
matter what port you pass; with several, any `--instance` form — valid or bogus — refuses
with a "multiple instances" error, as does omitting the flag (safe: it never guesses).

## Running tests

Run tests through the MCP bridge with the instance pinned: start a run with `run_tests` and
poll `get_test_job` for results. Run the fast EditMode suite (`FFEditorTests`) by default;
pass both `FFEditorTests` and `FFEditorTestsSlow` (or all EditMode assemblies) only when all
tests are explicitly requested. After making code changes, run the fast tests and verify they
pass before considering work complete. Only run slow tests if explicitly asked. **Confirm Burst
is enabled and idle before starting any run** — see the next subsection.

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
- **Runtime.** Managed job execution is roughly an order of magnitude slower. Measured
  2026-08-15: `FFPerformanceTests` took 476 s with Burst off versus ~45–60 s estimated with it
  on — ~13x, uniformly across production `KnnSystem` and benchmark jobs alike — which blew the
  test framework's default 180 s per-test watchdog (`UnityWorkItem.k_DefaultTimeout`) and
  reported a timeout failure that had nothing to do with the code under test.

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

**Never read `…/AppData/LocalLow/Never Games/finalfactory/TestResults.xml`** (or
`PerformanceTestResults.json`). The Unity Performance Testing package
(`com.unity.test-framework.performance`, a transitive dependency of `com.unity.entities` /
`com.unity.collections` — it cannot be removed) writes that file on *every* test run to a
path derived from `companyName`/`productName`, which is **shared by all FinalFactory
copies**. Whichever copy ran last clobbers it, so it will silently report another project's
results. The MCP job result is the only authoritative source. Trust ONLY the
`run_tests` / `get_test_job` result for the pinned instance.

### ⚠️ Long single-NUnit-test PlayMode jobs: two bridge defects (2026-08-07, M3, feature 049)

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
   go positive before believing its negative. (057 round 3, 2026-08-08: the beam re-anchor
   system's query required `WeaponOwner`, which no live beam owner carried — two shipped
   "fixes" in it had never run, and the second bug, a never-assigned `ComponentLookup` that
   threw on first scheduling, only surfaced when the query was fixed.)

**New `.cs` files**: an unimported script is not compiled at all — 0 errors + fresh domain
reload + green tests can all be true while your new file is absent from the build. Confirm the
`.meta` appeared next to it after refresh.

**Burst disabled**: `error CS` clean + green suite covers the C#/IL compile only. If Burst
compilation is off, no `BC` error can even be produced, so nothing here says the Burst path
builds. Enable Burst and let its queue drain before the run — see "Before ANY test run" above.

**Why not file-based checks**: they're slow and error-prone in a lot of edge cases (e.g. a
compile failure in the editor may never update the watched file, hanging the watcher forever).
Recover MCP first; if targeted recovery genuinely fails, report that compile/test proof
remains unavailable.

**Deterministic hooks back this ritual** (feature 061; the game repo's `.claude/settings.json`
+ `scripts/hooks/`, state under `Library/ClaudeHookState/`). What each signal means and how to
clear it:

- **Stop block listing `.cs` files** = those files were edited with no `refresh_unity` since.
  Clear it by running the ritual above (refresh → fresh domain reload → `error CS` check →
  fast suite if behavior changed), or state explicitly why verification isn't needed, then
  finish. It blocks once per turn-end, never loops.
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
a log-line marker didn't fire. For Log-level markers, use a state probe via `execute_code`
instead (it compiles via Roslyn on this Windows setup and works well; the old "execute_code
is broken on Windows" claim is outdated).

This applies to BOTH editors in a paired run — the clone (`../<project root>_clone_0`) has the
same stale-assembly trap (see the `determinism-audit` skill).

## Long background runs (player builds, paired audits, multi-minute test jobs)

Claude monitors and reports — the user must never have to ask "what's the verdict?". The
moment such a run starts, arm a Monitor on its log that fires on phase transitions AND every
terminal state (verdict lines, `error`/`Exception`, build failure, script exit — silence must
not be able to mean "crashed"), then post progress/verdicts to the user as the events land,
unprompted. A background task's completion notification alone is not enough for runs with
long silent phases (a 20-minute shader compile looks identical to a hang without a phase
monitor). Transitions alone are ALSO not enough — a single phase can take 20+ minutes, so the
monitor must emit a periodic progress heartbeat (~3 min: current phase + the underlying log's
last line). The user should see steady progress, never a gap long enough to make them ask.

## Building

Unity Editor menu `Build > Build and Upload All` (requires Steamworks SDK).

## Capturing editor memory

Use the MCP bridge — call `execute_code` to run a resident-memory breakdown that sums
`Profiler.GetRuntimeMemorySizeLong` per loaded-object category (Textures/Meshes/AudioClips/…)
plus engine totals (GfxDriver, Mono heap); `manage_profiler` covers profiler-marker captures.
(`Assets/Editor/MemorySnapshotTrigger.cs` still implements exactly this breakdown — mirror
its logic in the `execute_code` snippet.) It measures *editor-resident* memory (includes
editor-only objects), so it is for **relative before/after comparison in the same editor
state**, not absolute player numbers. This lets Claude measure memory changes itself instead
of asking the user to capture snapshots.
