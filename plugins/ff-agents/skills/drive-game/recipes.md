# Final Factory — proven gameplay recipes

Companion to `SKILL.md`. That file covers driving the **editor** safely (freeze diagnosis, `Step()`
rules, boot, screenshots, compiling). This file covers **playing the game**: every recipe below has
been proven live.

Read `SKILL.md` first — in particular the `Time.frameCount` rule and the `Step()` cap. Recipes here
assume you already know whether the editor is occluded or free-running.

> ⚠️ **`ffauto:` availability is branch-dependent.** Several recipes below use
> `ffauto:` commands via `LocalMultiplayerAutomationCommandRunner.TryExecute` (the feature-020
> harness), which lives on `develop`: neither `ffauto` nor `LocalMultiplayerAutomation` appears
> anywhere under `Assets/` on `master`. Grep before relying on it; where it is missing, use the
> `execute_code` equivalents.

## Driving the menus

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

**⚠️ Boot gate before ANY new game or load:** never invoke
`StartNewGame` or `SaveGameManager.LoadGame` until `FFCore.Extensions.Ecs.Ready &&
Ecs.HasSingleton<FFCore.Config.ItemConfig>() && Ecs.HasSingleton<FFCore.Config.MapGenerationData>() &&
Ecs.HasSingleton<FFCore.Fleet.CombatUpgradeContainer>()` returns true (namespace is `FFCore.Config`, NOT
`FFComponents`), then step ~200 more frames before the call. The singletons arrive one by one: w824's load started
with `ItemConfig` and `MapGenerationData` present and failed in `CombatUpgradesSystem.Reset` (from
`SaveGameManager.ResetGame`) with `GetSingleton<FFCore.Fleet.CombatUpgradeContainer>() requires that exactly one
entity exists`; the same load a few seconds later worked. That is the second miss of this kind (w761, w824): a
singleton list is a guess at "booted", so keep the extra frames even when every listed singleton is there. `ItemConfig` alone is not enough: a load
started when it was there and `MapGenerationData` was not ended at "Could Not Load Save" with
`GetSingleton<FFCore.Config.MapGenerationData>() requires that exactly one entity exists` (w761, the
editor stepped 30 frames after entering play mode); the same load a moment later worked. A `TitleScreenManager.Instance != null`
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
With the editor occluded the title-screen load flow needs PUMPED frames (the frame counter sits
still and `SaveProcessState` stays `Performing` forever): loop `EditorApplication.Step()` with a
real-time budget (100 steps took ~12 s mid-load) until `FFSystems.Core.ConfigInitializerSystem.GameStarted
&& <MePlayer exists> && Heartbeat.CurrentHeartbeatFrame > 40`; a 600-step loop that returns in 165 ms
did nothing (it ran before the load began). The built players' saves and the editor share
`SaveGamePath`, so a leg's checkpoint loads in the editor by name (074 T104/T105 probes).

⚠️ The `NewGame` save is a **modded** save and the editor disables mods, so it loads with missing
items/tech — pick a non-modded save for clean loads.

⚠️ **Runtime-provisioned state is absent while a loaded save is paused.** Components systems add after load
(the C3 vision holders, `C3KnnFleetVision`/`C3KnnEnemyVision`) do not exist until the save is unpaused (below) and
a few frames are pumped: w824 counted 0 holders on paused JustPlay and 37,049 after the unpause. Measure or query
them only then.

⚠️ **A loaded save can come in paused (`GameMetaState.IsPaused=true, GameStarted=false`) — never
clear it with a raw ECS write.** Setting the fields via
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

## Movement, mining, crafting, combat, research, placement, logistics

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
- **Logistics bots (requester and provider holds)** (w704): `ffauto:setting.requesterhold|<item>|<amount>|<x>|<z>`
  sets a Requester Cargo Hold's request (`docs/ffauto-command-reference.md`); the structure snapshot
  shows each hold's request, en-route amount and its bot's state. A live check needs a powered tower,
  provider and hold (the blueprint carries solar panels) and `player.devunlock` (a new game's supply bots
  carry 0 until the research), or it reads 0 delivered with nothing wrong in the code. Copy
  `scripts/nightly/scenarios/{SP,MP}-w704-requesters-fill.json`. How bots hold a task (`AssignedBot`):
  the game repo's `Documentation/ConstructionBots-Multiplayer-Issues.md`, "Who holds a task".

## Research, recipes, filters, fleet hand-off, and objective probing

Proven over tutorial objectives 50→63.

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
  FLEET, they do NOT auto-fly to stations): `ffauto:fleettransfer.deploy|<shipName>|<count>` makes the
  dispatch the Fleet panel's Deploy button makes (or press the button:
  `ffauto:ui.click|fleet|FleetElement[sprite=Bat]/Send`). The host sends the ships to the stations of the
  player's logistics network that take that ship and have room, in tile order; the panel's result line
  says how many moved. `fleet.stationships` counts the ships stations hold. Idle fleet ships sit ON the
  player's ship (`fleet.dumpstate` positions are world units), and a deployed ship parks beside its
  station only a few pixels wide at default zoom.
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

## Save-loads, mass drivers, power grids, inserters, and the final tutorial cards

Proven over tutorial objectives 63→78, to a finished tutorial.

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

## Heartbeat-exact build and deconstruct bench in the editor (w762, 2026-10-09)

Proven on lothdesktop, develop 0.50.0.90, flat single-player world. It was used to compare a change
against its revert: 200 Struts, 8 player Construction Bots, seed `w762-bench`. Build took 775 heartbeats
and deconstruction 790-791, repeatable to 1 heartbeat across runs.

- **Flat new game without the panel**: `TitleScreenManager` is internal, so call `StartNewGame` by
  reflection, with `UI.NewGame.NewGameSettings.CreateFromOldEnums(seed, ObjectivesMode.Off,
  AttackFrequency.Standard, EnemyDifficulty.Standard, FFNetcode.Lobby.LobbyCreationParameters.SinglePlayerGame)`
  and then `settings.FlatMap = true`. Wait for `IsMainMenuActive` and the `ItemConfig` singleton first (the
  boot gate above).
- **`ffauto:construction.place|<bp>|x|z` centres the blueprint on (x, z)**; it does not put its corner
  there. A 20×10 Strut grid placed at `0|10` covered tiles x −9..10, z 6..15, so a `construction.cut`
  rectangle worked out from the corner missed 116 of 200. After placing, read `Placeable.GridTile`
  min/max and cut that rectangle with a margin. (`scripts/nightly/make_blueprint.py` writes the grid.)
- **The placed blueprint stays in the player's hand.** Its copies are `PlayerPlaced` + `OutOfPlay` with
  no `ConstructionTaskData`, so count *built* = `!OutOfPlay && !ConstructionTaskData` and *remaining* =
  `!OutOfPlay || ConstructionTaskData`. A count of every `PlayerPlaced` entity never reaches 0.
- **Never `Thread.Sleep` in `execute_code` to wait.** It blocks the editor main thread, so no heartbeat
  runs during the sleep.
- **Heartbeat-exact timing**: from one `execute_code`, register an
  `UnityEditor.EditorApplication.update` callback that runs a small state machine: menu → new game →
  setup `ffauto` commands → settle N heartbeats → place → built == N (record the heartbeat, cut) →
  remaining == 0 (record). Each step writes progress to `UnityEditor.SessionState.SetString`. The
  callback unregisters itself when it is done or when `!Application.isPlaying`, and wraps its body in
  try/catch, logging to SessionState. Poll SessionState between turns (`wake_me`). To replace an armed
  hook, remove the `EditorApplication.update` delegates whose `Method.DeclaringType` comes from an older
  `MCPDynamic` assembly. Each `execute_code` compiles a new assembly, so a later call can find them.
- Revert the change under test with `git diff <merge>^1 <merge> -- <files> | git apply -R`, recompile,
  run the same hook again, then re-apply it.

## Real-save A/B of a simulation change in the editor (w870, 2026-10-10)

Proven on lothdesktop, develop 8caa350be: production and the full determinism fingerprint of a real save, at
develop and with a merged change reverted, to show whether the change alters anything a player has.

- **Pick a small real save.** Sandbox editors run with Burst OFF and the Jobs Debugger ON
  (`BurstCompiler.Options.EnableBurstCompilation` false). `MeltCPU.zip` (80,825 placeables, 676k entities)
  stepped at ~2.5 s per frame: unusable. The golden fixture
  `Assets/Tests/Serialization/Fixtures/TimTesting-0.50.0.92.save.bytes` (1,864 placeables, 49 crafters, 106 belt
  groups, 66 obelisks), copied into the saves folder as `<id>-TimTesting.zip`, loads in about a minute and steps
  7-8 heartbeats per second. Delete the copy when done.
- **Pump, don't wait.** With the editor unfocused an `EditorApplication.update` state machine advanced 13 frames
  in several seconds. Arm the state machine as in the w762 bench, then from each `execute_code` set
  `isPaused = true`, loop `EditorApplication.Step()` and invoke your `MCPDynamic` update delegate after each step,
  with a real-time budget of at most 18 s per call. A 25 s call timed out at the client and kept running queued.
- **Never autosave into the shared folder**: set the `AutosaveController` MonoBehaviour's `enabled = false`
  before `SaveGameManager.LoadGame`.
- **Measure** after the real unpause (`UI.UiController.UnpauseGame` + `FFSystems.SystemManager.ResumeAllFFSystems`
  by reflection), at a fixed heartbeat count, e.g. 160 to settle, then 960 (60 sim-seconds):
  `Ecs.GetSingleton<ProductionStats>().Serialize().TotalProductionStats` deltas per item id, and
  `DeterminismStateFingerprint.Compute(em)` + `ToWireSurfaces` (23 surfaces). The settle point came out at the
  same heartbeat (219) in both runs, and the two sides matched surface for surface (2,042 items, `4e1aa73554172709`).
  When the sides match, one run each is enough; when they differ, run the base side again before blaming the change.
- **Check which code is loaded** after each recompile before you trust a run: a field or nested type that only one
  side has, read by reflection (`InserterCargoJob.AllOutOfPlay` present or not). When later commits conflict with
  reverting the change, `git apply -3 -R <the commit's patch>` and resolve by hand.
- `execute_code` history is cleared by every domain reload, so `replay` does not survive a recompile: keep the
  arming script in a file of your own.
- **Single player is a Netcode host**: after a single-player load `NetworkManager.IsConnectedClient` and `IsHost`
  are both true, so code gated on `IsConnected` (e.g. `MiningAction.UsesSharedProgress`) runs in single player.
- An equivalence test with pinned values (old vs new code) needs a power check: reverse one loop or switch one
  rule off and confirm every case fails (w870: one reversed neighbour loop and "locks off" each changed all 6 seeds).

## Marketing and store stills from a built player (w827, 2026-10-10)

Proven on BEAST for Ben's Steam event cover (Build 92 release, 800x450). The finished covers were published
as att_czxzut77aptx, att_bewwrewxiy7h and att_8u6r6t4e4kw9.

- **A clean frame from a release player**: no HUD, and no "Development Build" text or fps counter. Run
  `python scripts/nightly/player_slots.py launch --detach <player dir> -- -ffAgentControl true
  -ffAgentControlDev true -ffAutomationRole solo -ffAutomationSave <save name> -screen-width 2560
  -screen-height 1440 -screen-fullscreen 0 -logFile <tmp log>`. `-ffAgentControlDev true` grants the dev
  tier even in a release build (`AgentChannelHost.ResolveCapabilities`, the flag is checked before
  `Debug.isDebugBuild`). Copy the save into the saves folder under a name of your own first, and delete
  your copy at the end.
- **The agent channel**: the port and token are in `<persistentDataPath>/AgentControl/session-<pid>.json`
  (`scripts/nightly/lab.py` `Peer` shows the requests).
  - `POST /v1/command {"actor":"local-player","command":"ffauto:ui.hide|true"}` hides the whole UI
    canvas. Without the `ffauto:` prefix the command is rejected.
  - `ffauto:camera.zoom|<distance>` sets the zoom. A smaller distance is closer, and the default framing
    is already wide.
  - `GET /v1/screenshot?maxEdge=1920` returns a PNG of the real frame. `maxEdge` must be 320..1920.
  - `ffauto:observe.state|nearby|x|z|r` caps the radius at 64 tiles, so scan a grid in 120-tile steps
    to find structures (for example, whether a save has mobile stations or holo pads).
- **Check the version you shot.** BEAST's Steam install reported `gameVersion` 0.50.0.83 on `/v1/hello`
  while develop was at 92. Say which build the frame came from.
- **Close the player with `(Get-Process -Id <pid>).CloseMainWindow()` in PowerShell.** The harness hook
  blocks `taskkill` from Bash. Then run `player_slots.py prune`.
- **The game's own key art is in the repo**: `Assets/Art/Textures/Final Factory_Artworks_02/{Building,Exploration}/PNG/*_Art_01.png`
  (9000x2700). Ben OK'd it for event covers: "you can also just generate something based on the
  illustrations for the game". A 4800x2700 crop is 16:9. The option recommended for the Build 92 event was a crop
  of Base Art, stations flying under thrust.
  - Logo: `Assets/Art/Branding/CenteredLogo.png`, white with its own drop shadow. Don't use
    `logoOnly.png`: its letters are semi-transparent.
  - Display font: Bebas Neue, in `Assets/Graph And Chart - Lite Edition/Themes/Common/Fonts/bebas_neue/`.
- **A Steam event cover is 800x450.** Composite at 1920x1080 with PIL, darkening the text side with a
  gradient, then downscale with LANCZOS. Look at a 400x225 copy for legibility.
  - Publish the first good option at once, then iterate on the person's own event text. Ben changed the
    headline mid-request, to "Being Reborn" instead of "Big Update".
