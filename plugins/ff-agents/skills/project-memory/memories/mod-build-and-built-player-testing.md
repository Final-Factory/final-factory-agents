---
name: mod-build-and-built-player-testing
description: "Building a mod project against the current game (Auto Reference off, the UnityLinker needs every reference, no FFSpaghetti/FFNetcode/QFSW.QC) and testing a mod in built players (shared mods folder window, probe mod, paired audit traps)"
metadata:
  node_type: memory
  type: project
  modified: 2026-10-07T15:10:00Z
---

**Lesson (w485, 2026-10-07, game 0.50.0.84, develop 4c0fe284c).** Gherik's four mods (Collector, FleetPatrol, ItemCannon, Repaint; his private repos) did not build against
the current game, and the merged mod template (`Final-Factory/FinalFactoryModTemplate` f21a859) does not either.

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

## Update w1227 (2026-10-13, game 0.50.0.103): the template builds again, and what Burst for mods does

- What 0.50.0.103's `FFSpaghetti.dll` needs, measured by `Assembly.ReflectionOnlyLoadFrom(...).GetReferencedAssemblies()`
  over the closure: `FFInput`, `FFConfiguration`, `FFTests`, `GraphAndChart`, `Graphy`, `QFSW.QC`, `FMODUnity`,
  `Unity.Physics.Custom` (game assemblies, copy them), the three `System.*` metadata DLLs, and the packages
  `com.unity.inputsystem` 1.19.0, `com.unity.localization` 1.5.12, `com.unity.visualeffectgraph` 17.3.0,
  `io.backtrace.unity`. With all of them present (each DLL with an Auto-Reference-off `.meta`, or `Unity.Physics.Custom`
  breaks netcode's compile with CS0234) the template's `Modding > Build X64 Mod` builds, so the earlier "never FFSpaghetti"
  advice holds only while its dependencies are missing. Template PR #12 has the list; `copy-finalfactory-dlls` copies it.
- `compile-check.sh` passes while the Unity build fails (it proves only the C#); `scripts/mod_api/template_check.sh
  --unity-build` in the game repo runs both. A project with no Library fails `-executeMethod` the first time ("class
  'ScriptBatch' could not be found"): import once first.
- **Burst for mods crashes the player.** The template's `ScriptBatch` never ships `<ID>_win_x86_64.dll` (it tests
  `File.Exists` on a path relative to the editor's working folder, and `BurstAotSettings_StandaloneWindows.json` has
  `EnableBurstCompilation: false`). Fixing both made a 22 MB library that holds a second copy of the game's Burst code
  (504 `FFSystems` references; the game's own library is 14 MB), and a 0.50.0.103 Windows player crashed at world creation in
  `burst.initialize.statics` when `BurstRuntime.LoadAdditionalLibrary` loaded it. `ProjectSettings/Burst_DisableAssembliesForPlayerCompilation.json`
  (every assembly but the mod's) left the size unchanged: the discard list drops roots only, the mod's references still
  pull the game's code in. Leave Burst off for mods until that is solved; no macOS dylib work is meaningful before.
- A test mod without Unity: compile it with the editor's `csc.dll` against the player's `Managed/` (FF*.dll, Unity.Entities,
  QFSW.QC ...), `dotnet csc @rsp` as `Tools/compile-check.sh` does; patch a member name in the DLL bytes (same length)
  to make a "stale API" mod. Install it in the shared `mods/` folder only for the run, launch through
  `player_slots.py launch <full-sha exe> -- ... -logFile <your log>` (a mistyped sha makes the launcher refuse and the
  copied `Player.log` is a STALE earlier run's: always pass `-logFile` and read that), remove it after.
- A mod can add Quantum Console `[Command]`s (a `static` method; the console scans the loaded assemblies; any console
  command locks the save's achievements). `ffauto:console.run|<command>` runs one in a tour (a `|` in an argument is read
  as the ffauto separator). Without a Steam client the Mods menu listed nothing until #1663 (NullReferenceException in
  `LoadModsList` and in the rows' `Item.State`).

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
