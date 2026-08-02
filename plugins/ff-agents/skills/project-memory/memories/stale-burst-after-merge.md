---
name: stale-burst-after-merge
description: "After a merge that changes DOTS job struct layouts, the editor can run STALE Burst-compiled jobs — NRE in Burst jobs while managed passes; force a Burst recompile, it's not a source bug"
metadata: 
  node_type: memory
  type: project
  originSessionId: 5283ba8b-e465-4f26-a90d-3829a4297ca6
  modified: 2026-07-28T05:32:40.876Z
---

Symptom: after merging a branch that changed ECS job structs (added/removed
`ComponentLookup`/closure fields → changed native struct layout), the editor's fast
EditMode suite showed a cluster of `NullReferenceException`s thrown "from a job compiled
with Burst" — e.g. `StationConnectionsSystem.OnUpdate` and `LogisticsStationSystem`'s
lambda job — cascading into ~25 failures (station-connection tests, heal-gate determinism,
and even downstream assertion failures in other systems like Tesla-arc / TerrainOreOverride).

Root cause: **stale Burst-compiled native code.** The C#/IL recompiled fresh on merge
import, but the editor kept running Burst native output whose struct layout no longer
matched the new managed structs → field-offset mismatch → NRE. It was NOT a source bug.

Proof it's Burst-staleness, not logic:
- Managed run passes cleanly (disable via `[BurstCompile]`→remove / `.WithBurst()`→
  `.WithoutBurst()` + recompile): all 629 tests green. Managed had safety checks ON, so a
  real bad access would have thrown there too — it didn't.
- Re-enabling `[BurstCompile]` + forcing a fresh recompile: still all green (verified with a
  SECOND targeted run so native Burst — not the async managed fallback — was exercised).

**How to apply:** if Burst-job NREs appear right after a big merge/rebase and the same code
passes on the source branch, don't hunt a source bug first — force a fresh Burst recompile
(touch/edit the offending system files, or clear `Library/BurstCache` / restart the editor)
and re-run.

Recurred 2026-07-28 after merge `df9714812`, with two refinements worth keeping:

- **Fastest decisive proof (~2 min, no file deletion):** flip
  `Unity.Burst.Editor.BurstEditorOptions.EnableBurstCompilation` to `false` by reflection via
  MCP `execute_code`, re-run the suite, flip it back. Burst-off green + Burst-on red = stale
  native code, full stop. (Expect the `execute_code` call that flips it to time out — Burst is
  tearing down/rebuilding; just re-query the property to confirm the new value.)
- **Toggling `Enable Compilation` off→on does NOT invalidate the JIT cache.** Verified: same 25
  failures returned after a full off/on cycle. Only wiping `Library/BurstCache/JIT` (editor
  closed) actually clears it — that fixed it here: 0 failures on two consecutive Burst-on runs
  afterward. Delete only `JIT/`, not the sibling `Windows-Intel/` (AOT cache for player builds).
  Before deleting, confirm no process holds the project: match `Win32_Process` `-projectPath`
  AND `ParentProcessId` (AssetImportWorker children inherit the `Unity.exe` name but list their
  own `-projectPath`), and check the project's instance is gone from `mcpforunity://instances`.
- **Cheap confirmation from the filesystem:** compare `Library/BurstCache/JIT/*.dll` mtimes to
  the merge commit time. In this instance the bulk of the cache was written 00:21–00:22 and the
  merge landed 00:27 — cached native code predating the IL it claims to represent. Burst's cache
  key evidently misses cross-assembly changes in *called* code (here `Filter.HasSelection` in
  FFComponents, added by `0b9941e83`, inlined into a FFSystems job whose own struct was
  unchanged), so a job can silently keep running pre-merge logic. Watch the async-Burst trap: right after a domain reload the first job invocation
may use the managed fallback (passes) before native is ready — run the suite twice (or use
synchronous Burst compilation) to be sure you tested the native path. See
[[feedback_test_command]].
