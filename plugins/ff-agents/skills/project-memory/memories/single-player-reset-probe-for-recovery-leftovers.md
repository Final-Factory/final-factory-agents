---
name: single-player-reset-probe-for-recovery-leftovers
description: "To find what a desync RECOVERY leaves on the client, do not build a paired leg -- in the main editor load the save through the DevLoadSave hook, census the kept-type signatures by reflection on `DeterminismStateFingerprintJobs.CollectCensusRecords`, call `SaveGameManager.Instance.ResetGame()` (the exact reset a recovery runs), census again, reload through the hook and census a third time: rows that survive the reset AND grow on the reload are the fork (073 T024: 24 -> 48 orphan route-display arrows, ~25 min end to end). Gotchas: the collector lives on the `...Jobs` type, `LoadGame` called from `execute_code` never ticked its coroutine (use the menu hook), and the loaded game sits in EDITOR pause (`EditorApplication.isPaused`) so every step needs a `Step()` pump."
---

# The single-player reset probe for recovery leftovers (073 T024, 2026-09-16)

**When.** The `census` surface is red on EVERY heartbeat of a post-recovery epoch but clean before it: a
set-size difference the recovery itself created. The diagnostic window cannot capture that epoch (it
latches on the first block after arming — [[census-fingerprint-surface-design]]), and a paired recovery
leg costs ~30 min per iteration. A recovery is `LoadGameFromMultiplayerRequest` -> `LoadGame` ->
`SaveGameManager.ResetGame()` -> deserialize (`SaveGameManager.cs:2937,810,1086`), so the single-player
load path runs the SAME reset; whatever survives it in single-player survives it on a recovering client.

**Recipe (main editor, ~25 min, `execute_code` with Roslyn works).**
1. `printf 'hazel1831\n' > dev_loadsave.trigger` (gitignored) and run menu
   `Final Factory/Dev/Load Save (from dev_loadsave.trigger)` — it enters play mode and loads once
   `ItemConfig` exists (`Assets/Editor/DevLoadSave.cs`). ~50 s; `===== LOAD PROFILE: <save> =====` in the
   editor log marks completion.
2. Census: `Type.GetType("FFSystems.Multiplayer.DeterminismStateFingerprintJobs, FFSystems")` →
   `CollectCensusRecords(EntityManager, bool includeTypeNames)` (internal static; the facade type
   `DeterminismStateFingerprint` does NOT have it) → rows are an internal struct with `Signature`,
   `Count`, `TypeNames` fields (NonPublic|Instance). Write `sig\tcount\ttypes` lines to the scratchpad.
3. `em.CompleteAllTrackedJobs(); Serialization.SaveGameManager.Instance.ResetGame();` then pump
   `EditorApplication.Step()` ×30 and census again — the survivors.
4. Reload through the SAME menu hook (a `SaveGameManager.LoadGame(...)` issued from `execute_code`
   started its coroutine but it never ticked — progress text stuck at "Unzipping 0 / 9" with
   `_processed=true`; the `EditorApplication.update`-driven hook works). After `UiController.PauseGame()`
   the EDITOR is paused (`EditorApplication.isPaused=true`), so the load only advances under a `Step()`
   pump: loop `Step()` ×100 until `GameMetaState.GameStarted && !IsPaused && placeables > N && hb > 20`.
5. Census a third time and diff with `join -t$'\t'` on the signature: survivors whose count GREW on the
   reload are the recovery fork; survivors at their old count are world infrastructure (singletons).
6. `manage_editor stop`.

**What it looks like when it works.** hazel1831: 157 rows / 35,385 entities → reset → 61 rows / 84
entities, every one at its pre-reset count → reload → the one non-singleton survivor (24 arrow entities)
at 48. After the fix, reset → 60 singleton rows, reload → 157 rows, arrows 24: identical to a first load.
Probe the survivors' provenance the same way (`ArrowDisplayMetaData.Parent`, `em.Exists`, the parent's
`LinkedEntityGroup`, `UpdateMarker` presence) before designing the fix.
