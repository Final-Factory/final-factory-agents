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

## Unity CLI fallback channel

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
pass before considering work complete. Only run slow tests if explicitly asked.

- **Editor tests** (fast): `Assets/Tests/` — FFEditorTests
- **Editor tests** (slow): `Assets/TestsSlow/` — FFEditorTestsSlow
- **Play mode tests**: `Assets/Scripts/PlayModeTests/` — FFPlayModeTests

**Never read `…/AppData/LocalLow/Never Games/finalfactory/TestResults.xml`** (or
`PerformanceTestResults.json`). The Unity Performance Testing package
(`com.unity.test-framework.performance`, a transitive dependency of `com.unity.entities` /
`com.unity.collections` — it cannot be removed) writes that file on *every* test run to a
path derived from `companyName`/`productName`, which is **shared by all FinalFactory
copies**. Whichever copy ran last clobbers it, so it will silently report another project's
results. The MCP job result is the only authoritative source. Trust ONLY the
`run_tests` / `get_test_job` result for the pinned instance.

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
