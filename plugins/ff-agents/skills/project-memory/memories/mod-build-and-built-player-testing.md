---
name: mod-build-and-built-player-testing
description: "Building a mod project against the current game (Auto Reference off, the UnityLinker needs every reference, no FFSpaghetti/FFNetcode/QFSW.QC) and testing a mod in built players (shared mods folder window, probe mod, paired audit traps)"
metadata:
  node_type: memory
  type: project
  modified: 2026-10-07T15:10:00Z
---

**Lesson (w485, 2026-10-07, game 0.50.0.84, develop 4c0fe284c).** Gherik's four mods (Collector, FleetPatrol, ItemCannon, Repaint; his private repos) did not build against
the current game, and the merged mod template (`bryding/FinalFactoryModTemplate` f21a859) does not either.

## Building a mod project (measured)

- Game DLLs auto-referenced -> 261 `CS0576` from FFCore's global `Debug`: Auto Reference off in the tracked
  `.meta` (`isExplicitlyReferenced: 1`), the mod asmdef lists them in `precompiledReferences`
  ([[mod-template-global-debug-autoreference]]). `Assets/Editor` scripts (ScriptBatch) then need their own
  `*.Editor.asmdef`, and with `overrideReferences` a package DLL (`Newtonsoft.Json.dll`) must be listed too.
- Unity 6's UnityLinker runs in a Mono player build even with managed stripping Disabled and resolves EVERY
  reference of every DLL in the build (`ILLink error IL1010 ... failure in processing 'FFCore' reference`).
  FFCore needs `System.Reflection.MetadataLoadContext`, `System.Reflection.Metadata`,
  `System.Collections.Immutable` (in the game's `Managed/`; [[modloader-metadata-inspection]]) copied beside
  it; `validateReferences: 1` on FFCore without them makes Unity refuse FFCore, so no editor script compiles
  ("executeMethod class 'ScriptBatch' could not be found" — the template's state today).
- `FFSpaghetti` (FMOD, Steamworks, Backtrace, Graphy, Services...), `FFNetcode` (Facepunch.Steamworks.Posix in a
  Mac player's copy, Win64 in a Windows one: a cross-copied FFNetcode breaks the other target) and `QFSW.QC`
  (Input System) cannot be in a mod project. A mod that needs `NetworkOperations.Settings`
  (`StructureSettingAppliers.Register`, `StructureSettingsDispatch.DispatchSetting`) reaches it by reflection
  (`Assets/Scripts/GameActions.cs` in three of Gherik's mods). Working set: FFCore, FFComponents, FFSystems,
  FFTechnology, FFConfiguration + the three System.* DLLs.
- Gherik's ScriptBatch builds Windows only (Windows support is installed on the M5; Mac players need
  StandaloneOSX asset bundles). A compile check without Unity: Unity's Roslyn (`NetCoreRuntime/dotnet
  DotNetSdkRoslyn/csc.dll`) with the rsp of `Library/Bee/artifacts/*P.dag/FFSpaghetti.rsp` (player DLLs,
  Entities generators) and the mod's sources.

## Testing a mod in built players

- Players read only the shared `persistentDataPath/mods/` (`FF_EDITOR_MOD_PATH` is editor-only). Install mod +
  probe, launch, and remove both once each player logged `Mods finished post init` and its game started
  (bundles load in PostInitializationHook/OnGameStart); enabled mods on disk make every player on the Mac
  count as modded.
- The `-ffAutomationRole` localhost path does not call `BlockMultiplayerIfModded`, so
  `scripts/audit/run_build_multiplayer_audit.sh --skip-build` (FF_BUILD_DIR = the build's `player/`,
  FF_LOG_DIR = yours) runs a modded pair with the fingerprint verdict. A reused `--label` fails the report
  ("Audit artifact identity collision"); give the players movement or its playerSimPos check exits 5.
- Mod UIs read legacy `UnityEngine.Input`, which ffauto cannot press. A test-only probe mod (a MonoBehaviour
  added in OnGameStart; no ECS systems, so no ILPP needed) calls the mod's own request method and writes a
  digest per heartbeat keyed by `FFTimeData.simulationElapsedTime.RawValue`; compare host vs client. The
  client's first sample at the join precedes the snapshot's buildings: one expected differing line.
- Fixtures: `make_blueprint.py` `slots` must list the structure's whole slot buffer, or
  BlueprintInstantiatorSystem Burst-aborts the player. Hand mining makes no pickupables any more. Research
  drops credit only on biome tiles; `loot.prepareflatbiome` maps ±256 tiles around the player (run it on every
  peer), and `loot.preparedeath|research` on the host after the join reaches clients as a LootSpawn op (lands
  near x = player − 256).
