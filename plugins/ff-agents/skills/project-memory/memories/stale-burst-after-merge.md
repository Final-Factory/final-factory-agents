---
name: stale-burst-after-merge
description: "Burst can be switched OFF entirely (check EnableBurstCompilation before every test run — a green suite then proves nothing about the Burst compile, and runs ~10x slower); it compiles ASYNCHRONOUSLY — an empty console right after refresh_unity proves nothing; wait on BurstLoader.BurstProgressId first. And after a merge that changes job structs or their callees, the editor can run STALE Burst native code (NRE) or fail to resolve new types (BC1054) — wipe Library/BurstCache/JIT, it's not a source bug"
metadata: 
  node_type: memory
  type: project
  originSessionId: 5283ba8b-e465-4f26-a90d-3829a4297ca6
  modified: 2026-08-10T01:40:00.000Z
---

## ZEROTH: Burst may be switched OFF entirely — check before every test run

Everything below assumes Burst is actually compiling. It is an editor setting and it can be
off, with no signal anywhere:

```csharp
var o = Unity.Burst.BurstCompiler.Options;
var was = o.EnableBurstCompilation;
if (!was) o.EnableBurstCompilation = true;   // == Jobs > Burst > Enable Compilation
return new { was, now = o.EnableBurstCompilation };
```

With it off, every job runs managed: a suite can go green while the Burst compile is broken
(no `BC` error can be produced at all), and the run is roughly 10x slower — measured
2026-08-15, `FFPerformanceTests` at 476 s vs ~45–60 s, which then failed on the test
framework's default 180 s watchdog for reasons unrelated to the code. Enabling it queues a full
background compile, so wait it out per the section below before starting the run. The binding
pre-test rule lives in the `editor-ops` skill ("Before ANY test run"); say so in your report if
you turned it on, since it is persistent and the user may have disabled it on purpose.

## FIRST: you cannot read Burst's results until Burst has FINISHED

Burst JIT-compiles in a **background** queue. `refresh_unity` returning, `ready_for_tools`
being true, and `compilation.is_compiling` being false all say nothing about it — those cover
the C#/IL compile only. Reading `read_console` right after a refresh and finding no Burst
errors is **not evidence that Burst succeeded**; it usually means Burst has not gotten there
yet. (Ben caught exactly this overclaim on 2026-08-09 — I declared BC1054 errors fixed while
Burst was still at 43/44 libraries.)

The readiness signal is `Unity.Burst.Editor.BurstLoader.BurstProgressId`, a
`UnityEditor.Progress` item id. While the queue is draining it is a live id whose description
reads `"Compiled N / M libraries"`; when the queue empties Burst resets it to `-1` and
`Progress.Exists(id)` goes false. Poll it via MCP `execute_code`:

```csharp
var bl = System.Type.GetType("Unity.Burst.Editor.BurstLoader, Unity.Burst");
var f  = bl.GetField("BurstProgressId", System.Reflection.BindingFlags.Static
                   | System.Reflection.BindingFlags.NonPublic
                   | System.Reflection.BindingFlags.Public);
var id = (int)f.GetValue(null);
var busy = id != -1 && UnityEditor.Progress.Exists(id);
return new { busy, id, desc = busy ? UnityEditor.Progress.GetDescription(id) : "(idle)" };
```

Only once `busy` is false does a clean console mean anything. **Never report "Burst is clean"
without having observed that transition** — say "Burst still compiling (N/M)" instead.

**Strongest available proof** (use when the verdict matters, e.g. gating a merge commit): set
`Unity.Burst.BurstCompiler.Options.EnableBurstCompileSynchronously = true`, clear the console,
run the suite, then restore it to `false`. Every job then Burst-compiles natively at schedule
time, so a BC error cannot hide behind the async managed fallback. Its one limit, which you
must state rather than paper over: it only covers jobs the suite actually **schedules** —
broader coverage still comes from the eager background pass above. This supersedes the older
"just run the suite twice" advice.

**Scanning the console reliably:** MCP `read_console`'s `types` and `filter_text` filters
returned unrelated entries in practice (a `types:["error"]` + `filter_text:"Burst"` query came
back with an unrelated gameplay log line). Enumerate `UnityEditor.LogEntries` by reflection
instead — `StartGettingEntries()` / `GetEntryInternal(i, entry)` / `EndGettingEntries()` — and
match the text yourself against `BC1`, `Burst error`, `Burst internal compiler error`,
`error CS`, `Unable to resolve type`. `LogEntries` is internal, so reach it via
`System.Type.GetType("UnityEditor.LogEntries, UnityEditor")`, not directly (`execute_code`
fails with "inaccessible due to its protection level").

## Symptom A — stale native code: NREs in Burst jobs, managed passes

After merging a branch that changed ECS job structs (added/removed `ComponentLookup`/closure
fields → changed native struct layout), the fast EditMode suite showed a cluster of
`NullReferenceException`s thrown "from a job compiled with Burst" — e.g.
`StationConnectionsSystem.OnUpdate` and `LogisticsStationSystem`'s lambda job — cascading into
~25 failures (station-connection tests, heal-gate determinism, and downstream assertion
failures in other systems like Tesla-arc / TerrainOreOverride).

Root cause: **stale Burst-compiled native code.** The C#/IL recompiled fresh on merge import,
but the editor kept running Burst native output whose struct layout no longer matched the new
managed structs → field-offset mismatch → NRE. NOT a source bug.

Proof it's Burst-staleness, not logic:
- Managed run passes cleanly (disable via `[BurstCompile]`→remove / `.WithBurst()`→
  `.WithoutBurst()` + recompile): all 629 tests green. Managed had safety checks ON, so a real
  bad access would have thrown there too — it didn't.
- Re-enabling `[BurstCompile]` + forcing a fresh recompile: still all green (verified with a
  SECOND targeted run so native Burst — not the async managed fallback — was exercised).

## Symptom B — BC1054 blaming files that never mention the type (2026-08-09)

Merging `origin/master` into `develop` (new component `FFComponents.Heat.OverheatingState`,
consumed by `StationGridCalculationSystem`) produced:

```
Burst internal compiler error: ... Could not find type `a87262a7b89a851cb27d938d9f3fac61`
  in assembly `Burst.Compiler.IL.AssemblyNameReferenceAndMetadata`
SignalDampenerAnimationSystem.cs(40,7): Burst error BC1054: Unable to resolve type
  `FFComponents.Heat.OverheatingState. Reason: Unknown.`      (also AssemblerAnimationSystem,
                                                               ResearchStationPowerSystem)
```

**The blamed files do not reference `OverheatingState` at all** — grep proves it. The reported
line is each system's `[BurstCompile] OnUpdate`, which calls a *static* on
`StationGridCalculationSystem` (`NumCalcStepsSinceLastUpdate`,
`WereCalculatedGridsUpdatedLastUpdate`); Burst inlines that callee and drags its type
references in. So **a BC1054 naming a file that cannot reference the type is a cache/resolver
failure, not a source bug** — same cross-assembly-callee blind spot as the mtime note below.
The GUID-named type in a nonexistent assembly is the corroborating tell: that is Burst's own
internal reference table, never user code.

Fix: wipe `Library/BurstCache/JIT` with the editor closed, restart, let the background compile
drain (see above). Result here: 0 Burst/CS entries across all 77 console entries, and 2460
tests green with synchronous Burst on.

## How to apply

If Burst-job NREs or BC1054s appear right after a big merge/rebase and the same code passes on
the source branch, don't hunt a source bug first — clear the cache and re-run.

- **Fastest decisive proof (~2 min, no file deletion):** flip
  `Unity.Burst.Editor.BurstEditorOptions.EnableBurstCompilation` to `false` by reflection via
  MCP `execute_code`, re-run the suite, flip it back. Burst-off green + Burst-on red = stale
  native code, full stop. (Expect the `execute_code` call that flips it to time out — Burst is
  tearing down/rebuilding; just re-query the property to confirm the new value.)
- **Toggling `Enable Compilation` off→on does NOT invalidate the JIT cache.** Verified: same 25
  failures returned after a full off/on cycle. Only wiping `Library/BurstCache/JIT` (editor
  closed) actually clears it — that fixed it both times. Delete only `JIT/`, not the sibling
  `Windows-Intel/` (AOT cache for player builds). Before deleting, confirm no process holds the
  project: match `Win32_Process` `-projectPath` AND `ParentProcessId` (AssetImportWorker
  children inherit the `Unity.exe` name but list their own `-projectPath`), and check the
  project's instance is gone from `mcpforunity://instances`. Re-pin the instance after
  restarting — **ports get reassigned across restarts**, so pin by `Name@hash` from
  `mcpforunity://instances`, never by remembered port.
- **Cheap confirmation from the filesystem:** compare `Library/BurstCache/JIT/*.dll` mtimes to
  the merge commit time. In the 2026-07-28 instance the bulk of the cache was written
  00:21–00:22 and the merge landed 00:27 — cached native code predating the IL it claims to
  represent. Burst's cache key evidently misses cross-assembly changes in *called* code (there
  `Filter.HasSelection` in FFComponents, added by `0b9941e83`, inlined into an FFSystems job
  whose own struct was unchanged), so a job can silently keep running pre-merge logic.

See [[feedback_test_command]].
