# Final Factory — proven gameplay recipes

Companion to `SKILL.md`. That file covers driving the **editor** safely (freeze diagnosis, `Step()`
rules, boot, screenshots, compiling). This file covers **playing the game**: every recipe below was
proven live on the dates noted.

Read `SKILL.md` first — in particular the `Time.frameCount` rule and the `Step()` cap. Recipes here
assume you already know whether the editor is occluded or free-running.

> ⚠️ **`ffauto:` availability is branch-dependent.** Several recipes below use
> `ffauto:` commands via `LocalMultiplayerAutomationCommandRunner.TryExecute` (the feature-020
> harness). Verified 2026-08-01 on `master`: neither `ffauto` nor `LocalMultiplayerAutomation`
> appears anywhere under `Assets/` on that branch — the harness lives on `develop`. Grep before
> relying on it; where it is missing, use the `execute_code` equivalents.

## Driving the menus (proven 2026-07-12)

The whole menu surface is uGUI and fully drivable from `execute_code` — no mouse needed. Full flow
proven: title menu → New Game panel → Begin Game → world-gen → in-game HUD, then in-game menu →
Load panel → select save → loaded.

**State probe (where am I?)** — menu classes are `internal`, so resolve via reflection:
```csharp
System.Type tsm = null;
foreach (var asm in System.AppDomain.CurrentDomain.GetAssemblies()) { tsm = asm.GetType("Behaviours.TitleScreenManager"); if (tsm != null) break; }
var mode = tsm.GetProperty("CurrentMode", System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static).GetValue(null); // TitleScreen | InGame
var inst = tsm.GetProperty("Instance", System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.FlattenHierarchy).GetValue(null);
// also on inst: IsMainMenuActive, IsLoading (instance props, may be non-public)
```

**Click any menu button by its label.** Buttons are `UnityEngine.UI.Button` with TMP labels; the menu
lives at `PersistentObjects/Canvas/MainMenuPanel(Clone)`. Title-screen buttons: New Game, Load Game,
Settings, Report Bug, Multiplayer, Mods, Test Builder, Test Runner, Credits, Exit Game. In-game menu:
Save, Load Game, Settings, Report Bug, Exit to Menu.
```csharp
var buttons = UnityEngine.Object.FindObjectsByType<UnityEngine.UI.Button>(UnityEngine.FindObjectsInactive.Exclude, UnityEngine.FindObjectsSortMode.None);
foreach (var b in buttons) { var l = b.GetComponentInChildren<TMPro.TMP_Text>(true);
  if (l != null && l.text == "New Game") { b.onClick.Invoke(); break; } }
// then pump Steps so the panel opens/animates
```

**⚠️ Boot gate before ANY new game (cost a stranded world, 2026-08-10):** never invoke
`StartNewGame` until `FFCore.Extensions.Ecs.Ready && Ecs.HasSingleton<FFCore.Config.ItemConfig>()`
returns true (namespace is `FFCore.Config`, NOT `FFComponents`). A `TitleScreenManager.Instance != null`
probe passes far too early (frame ~20 on a fresh boot); starting a game mid-boot strands the world —
missing `ItemConfig`/`MapGenerationData` singletons, an NRE in `TitleScreenManager.PrepareSceneForGame`,
and `MePlayer` never appears, with no loud failure at the call site.

**Start a new game**: click `New Game` → the panel opens (world-type tabs
Standard/Explorer/Hardcore/Custom, pre-rolled seed field, Tutorial/Enemy Difficulty/Attack Frequency
toggles) → click `Begin Game` → pump ~200+ steps for world-gen → probe `CurrentMode == InGame`.
Programmatic alternative, skipping the panel:
`TitleScreenManager.Instance.StartNewGame(NewGameSettings.Create(...))` — see
`Assets/Scripts/UI/NewGame/NewGameSettings.cs` for the factory methods.

**Open the in-game menu**: inject `escape` via the trigger file, or reflectively call `ShowMenu(true)`
on the `TitleScreenManager` instance (both work; `ShowMenu` is direct).

**Load a save**: click `Load Game` (works from BOTH the title menu and the in-game menu) → the Load
panel lists saves sorted by date. ⚠️ **Save rows are NOT Buttons — they are `Toggle`s**
(`ListItem(Clone)` with `SelectionItem`/`ToggleHelper` in a `ToggleGroup`): find the Toggle whose
child TMP text equals the save name, set `toggle.isOn = true`, pump a few steps, then click the
panel's `Load Game` button (distinguish it from the menu button of the same name: the panel's has
parent `ButtonPanel`), then pump ~300 steps and re-probe. Enumerate saves on disk first:
```csharp
var dir = Serialization.SaveGameManager.SaveGamePath;
var files = System.IO.Directory.GetFiles(dir, "*.zip"); // filename minus .zip = the name shown in the UI
```
Headless alternative without UI (what `Assets/Editor/DevLoadSave.cs` does):
`Serialization.SaveGameManager.LoadGame(FFNetcode.Lobby.LobbyCreationParameters.SinglePlayerGame, "<saveName>", true)`.

⚠️ The `NewGame` save is a **modded** save and the editor disables mods, so it loads with missing
items/tech — pick a non-modded save for clean loads.

⚠️ **A loaded save can come in paused (`GameMetaState.IsPaused=true, GameStarted=false`) — never
clear it with a raw ECS write** (proven 2026-08-04, 057 US3 probe leg). Setting the fields via
`EntityManager.SetComponentData` clears the flag but leaves EVERY `FFSystems.*` system/group
disabled at the World level (`SystemManager.PauseAllFFSystems()`'s effect persists). The decoy:
`Heartbeat.CurrentHeartbeatFrame` keeps advancing while `FFTimeData.realElapsedTime` and all sim
state (e.g. `Crafter.CraftProgress`) stay frozen — it looks like a sim bug, not a pause. The real
unpause path is `UI.UiController.UnpauseGame()` then `FFSystems.SystemManager.ResumeAllFFSystems()`
— both `internal`, call via reflection. Verify recovery by checking a system's
`SystemState.Enabled` flipped to true and `realElapsedTime` advances.

**Screenshots (menus/HUD included)**: the capture mechanics live in ONE place — `SKILL.md` →
"📸 Screenshots — THE canonical recipe" (Free Aspect prerequisite, the composited `manage_camera`
channel vs `ScreenCapture` + focused GameView, and the never-`gv.Focus()`-with-a-blueprint-in-hand
trap). Don't re-derive them here.

## Session 1 (2026-07-12) — movement, mining, crafting, combat, research, placement, logistics

Proven driving the full early tutorial with the editor occluded (Step-pumped).

- **Movement / flying somewhere**: `ffauto:movement.hold|x|z|seconds`. Find world targets via ECS
  queries (e.g. nearest "Silica Asteroid" by `AsteroItem.ConfigIndex` name) instead of reading
  indicators. **Player flight speed ≈ 96 u/s**; `movement.hold` overshoots — fly a main leg plus a
  short correction leg, re-probing position between.
- **Manual mining**: `ffauto:mining.startnearest` mines a burst then stops (a human HOLDS
  right-click) — re-issue in a loop (~350 steps between re-arms) until the objective count is done.
  One burst ≈ +26 ore. The `|<maxRange>` arg can false-negative on y-offset terrain (asteroid roots
  sit at y=-120); omit it.
- **Crafting panel**: open with the `PlayerManagement` HUD button (`Button.onClick.Invoke()` works).
  Category tabs are `Toggle`s under `TabPanel` (`LogisticsTab`, `CombatUnitsTab`, `ComponentsTab`,
  `InfrastructureTab`, `ProductionTab` — Production appears only after Mining Logistics research).
  **Craft buttons (`CraftButton(Clone)`) do NOT craft via `Button.onClick`** — they use
  `AltClickHandler` (`IPointerClickHandler`); send a real EventSystem click:
  ```csharp
  var pe = new UnityEngine.EventSystems.PointerEventData(UnityEngine.EventSystems.EventSystem.current)
    { button = UnityEngine.EventSystems.PointerEventData.InputButton.Left };
  UnityEngine.EventSystems.ExecuteEvents.Execute(craftButtonGO, pe,
    UnityEngine.EventSystems.ExecuteEvents.pointerClickHandler);
  ```
  Identify a recipe by its child `Image.sprite.name` (`Bat`, `MiningDrone`, `SolarPanel`, `Connector`,
  `CargoHold`, `MiningStation`…). Left click = craft 1. Ship crafts land in the *Fleet Craft Queue*,
  item crafts in the *Item Craft Queue* (both bottom-left; the SmartCrafter auto-queues the whole
  intermediate tree).
- **Abilities**: hotbar `AbilitySlot` buttons also ride `AltClickHandler` — send `pointerDown` +
  `pointerClick` to activate (proven: afterburner dash runs its full coroutine). Frenzy-style targeted
  casts: create the cast entity directly — `em.CreateEntity(typeof(FrenzyCastMarker))` +
  `CastArgs{AbilityType, Position}` — and if an objective needs credit, ALSO
  `AbilityNotifierService.Instance.OnAbilityUsed?.Invoke(type)` (the objectives tracker hangs off that
  event, not the marker).
- **Structure placement — use the remote-apply path, NOT `ffauto:construction.place`, in a live solo
  session**:
  ```csharp
  var placed = Blueprints.BlueprintTool.InstantiateAndPlaceBlueprintFromString(bpStr, tile,
      Ecs.GetSingletonEntity<FFCore.Blueprints.BlueprintMaster>(), true);
  NetworkOperations.Blueprints.BlueprintPlacementNetworkOperation.EnsureConstructionTasks(placed);
  NetworkOperations.Blueprints.BlueprintPlacementNetworkOperation.EnsureTerrainExtractorTargets(placed);
  ```
  This is exactly what a non-originating peer does; the frame persists, the construction bot builds it
  (~1–2 s), and terrain extractors resolve their asteroid target. Author a one-item blueprint in code
  (`Blueprint` + `BlueprintMetaItemManaged{ItemName, Length, Width, OriginalDirection}`,
  `GetFullBlueprintString`). Placement facts: tiles are 10 world units, `Placeable.GridTile` is the
  min corner, `Direction.Up=+z/Right=+x`; a Mining Station is only placeable while an asteroid is
  within `NetworkRadius(16) × GridSize(10)` of the station center — center-to-CENTER, so hug the
  asteroid edge.
  - Why not `construction.place`: its pass-2 commit + `ConfirmGhostsForOutcome` re-anchor math needs
    blueprint strings captured from REAL copies (the audit path); hand-authored strings with declared
    dims ≠ real footprint get their committed frame silently deleted at outcome-apply
    (`ComputeReanchorMidpoint` mismatch), and each failed attempt strands a preview ghost that makes
    the NEXT attempt invalid (overlap). If you do use it: purge stray `BlueprintItemMarker` entities
    between attempts.
  - If ghost/route-display cleanup goes wrong you'll see per-frame `ArgumentException: The entity does
    not exist` spam from `LogisticsRouteDisplaySystem` — destroy the `LogisticsDisplayReferences`
    entities whose `RouteDisplay` no longer exists.
- **Structure removal**: `ffauto:construction.remove|<centerTile.x>|<centerTile.z>` (the 016 queue
  path) works in live solo sessions — cbot deconstructs and refunds the item (~2 s).
- **Withdrawing from a structure** (tutorial "collect ore", Ctrl+click equivalent):
  `FFInventory.Inventory.From(station).RemoveItems(...)` + `Inventory.From(player).AddItems(...)`,
  then `AbilityNotifierService.Instance.OnItemsCollectedFromBuilding?.Invoke(n)` for objective credit.
- **Objectives**: read progress from the `ObjectivesTracker` ECS singleton; the on-screen objective
  panel is the source of truth for what's asked — screenshot and Read it. Every objective also has a
  `Complete` (skip) button — don't use it in a playtest; complete objectives for real.
- **Tech/research**: `TechButton` HUD button opens the Technologies panel (the tutorial pre-selects the
  target tech); click the `Research`-labelled button, then `Dismiss` on the unlock dialog. Research
  completes instantly if banked points ≥ cost.

## Session 2 (2026-07-13) — tutorial objectives 50→63

- **Research a SPECIFIC tech programmatically** (when the panel doesn't pre-select it): reflect
  `UI.Panels.TechnologySelectionPanel`, call private `SelectTechnology(string, bool, bool)` with the
  tech's `_name` field from `Assets/Resources/Technologies/<X>.asset` — it has SPACES (e.g.
  `"Ship Assembly"`, NOT the asset filename) — then private `OnResearchPressed()`.
- **Set a crafter/assembler recipe** (the UI's own networked op, tile-keyed):
  `NetworkOperations.Cheats.CheatCommandDispatch.Dispatch(SetCrafterRecipeRequest, SetCrafterRecipe,
  CheatCommandPayloads.Serialize(new SetCrafterRecipePayload { RecipeName =
  itemConfig.IdToNameLookup[id].ToString(), TileX/Y/Z = placeable.CenterTile }))`.
- **Set a connector filter**: `Helpers.FilterHelper.DispatchFilter(connectorEntity,
  new FFComponents.Stations.Filter { FilterItem = itemId })` — also rides the op queue.
- **Deposit fleet ships at a station** (fleet→factory hand-off; manually-crafted miner bots land in the
  FLEET, they do NOT auto-fly to stations): reflect `UI.Panels.Fleet.PlayerFleetPanel`, call private
  static `DeployShipToNavigationNetwork(itemId, count)`. Player must be in/near the target station's
  logistics network (fly within ~100 units first).
- **Blueprint placement re-anchor gotcha**: 1×1 and 2×2 items land EXACTLY at the paste tile, but a
  width-3 item (Mining Station 2×3) landed shifted −1 in x — ALWAYS re-read `Placeable.GridTile` after
  placement instead of assuming. `placed.Count==0` means the spot was blocked (skipBlockedStructures
  silently skips) — probe free tiles first via
  `Ecs.GetSingleton<FFComponents.Map.FFGrid>().EntityMap.TryGetValue(tile, out _)` (asteroids occupy
  large tile blobs).
- **"Is it built yet?"**: a placed frame is NOT built until it loses `OutOfPlay` +
  `ConstructionTaskData` — absence of `BlueprintItemMarker` is NOT sufficient. The cbot fetches the
  item from the PLAYER's inventory: stay near the site or the task sits pending.
- **Factory "stalled"? Check power FIRST**: crafters run at
  `StationGridPowerConsumer.SatisfactionRatio` speed (0.28 observed = 3.5× slowdown that looks like a
  stall). Fix = more solar panels pointing INTO a grid structure.
- **Two craft queues**: `ItemCraftQueue` and `FleetCraftQueue` are separate `CraftingQueuePanel`
  instances — find by `gameObject.name`, not `FindFirstObjectByType` (which returns either).
- **Active objective probe**: reflect `GameRunning.Objectives.ObjectivesController`, read private
  property `ActiveObjectives`, `ToString()` each entry. The objective's Verifier asset (+ its
  `m_Script` guid → class in `GameRunning/Objectives/Verifiers/`) tells you EXACTLY what completion
  requires — read it before grinding.
- **Inventory withdraw/deposit**: `FFInventory.Inventory.From(entity)` +
  `RemoveItems(id, n, true, InventoryType.All)` / `AddItems(id, n, true, InventoryType.Primary)`;
  re-acquire `Inventory.From` after ANY pumped frames (the cached buffer invalidates on structural
  change).

## Session 3 (2026-07-13) — tutorial objectives 63→78 (tutorial finished)

- **⚠️ Entity handles are NOT stable across save-loads.** A cached `Entity{Index,Version}` from a
  previous session throws `component has not been added` after reloading the same save — always
  re-find structures by `Placeable.GridTile` (tiles ARE stable) after any load.
- **Set a mass driver's destination** (the UI's networked op):
  `NetworkOperations.Settings.StructureSettingsDispatch.DispatchSetting(
  StructureSettingKind.MassDriverTarget, sourceDriverEntity, new EntityTargetPayload {
  TargetTileX/Y/Z = <any tile of the destination driver> })`. Mass Driver `NetworkRadius` = 40 tiles
  (400 world, center-to-center; `LogisticsUnitConfigLookup[116].NetworkRadiusFp`).
- **Re-anchor shift generalizes**: paste tile == landed `GridTile` only for 1×1/2×1/2×2; the 2×3 mining
  station shifted −1 in x, and the 3×4 research station shifted −1 in BOTH x and z (and `placed=0` when
  that shift collided with a neighbor). For big footprints: offset the paste tile +1 to compensate, or
  place, read back `GridTile`, and retry.
- **Solar panels only power the structure they POINT INTO** — a structure merely touching a panel's
  side (or another powered structure) does NOT join that power grid. Every isolated structure cluster
  (lone mass driver, research station) needs its own panel aimed at it (`power=0` until then;
  verifiers like PlaceAndPowerStation gate on satisfaction > 0).
- **Inserters**: `Inserter Bot` is an ITEM craft placed like a structure (1×1, floats at grid y=1).
  Place with arrows AWAY from the source: its START endpoint lands on the structure behind it and it
  picks up automatically once built (cargo visible in its `Cargo` buffer). An unbuilt frame does
  nothing — same OutOfPlay rule as everything else.
- **Map / fleet panel objective events**: map counts on CLOSE (`WorldMapControlAction.OpenMap()` +
  `CloseMap()` via reflection); fleet panel via static `UI.UiController.HandleFleetTogglePressed()`
  (reflection — class is internal; the first call may just close other open panels and return False →
  call again).
- **The final tutorial card (78) uses the `DontVerify` verifier** — clicking its `Complete` button IS
  the designed completion, not a skip.
- **PlayerManagement HUD button TOGGLES the crafting panel** — after any flight/close, re-probe
  `CraftButton` count and click it again if 0 (clicking blindly can close an open panel).
- Craft-button count labels can be STALE right after resources change — a click can succeed even when
  the label still reads 0; trust the queue probe, not the label.
