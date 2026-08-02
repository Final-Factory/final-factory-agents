---
name: itementities-baking-pipeline
description: "How Resources/ItemEntities/*.prefab (Player, etc.) become instantiable ECS prefabs, and how to author + verify companion entities on them"
metadata: 
  node_type: memory
  type: reference
  originSessionId: db2f089c-89c7-4713-a675-000f660fad79
---

The base-game entity prefabs under `Assets/Resources/ItemEntities/*.prefab` (e.g. `PlayerEntity.prefab` = the "Player" prefab) **are baked through standard Unity subscene baking**, despite the presence of the runtime `GameObjectEntityConverter` (which only builds *model/render* child entities, and only for the mod path in `ModInitializer`).

Bake path: `EntityPrefabContainerBaker.Bake()` (`Assets/Scripts/FFComponents/Initialization/EntityPrefabContainerAuthoring.cs`) calls `GetEntity(item.EntityPrefab)` for every managed `FFItemConfig`, which bakes each prefab's authoring MonoBehaviours (`PlayerBaker`, `KnnEnemyVisionBaker`, …) into an entity prefab with a `LinkedEntityGroup`. Those baked entities land in the `FfItemEntityPrefab` buffer, read at play start by `StartController` → `ConfigLoadingUtil.CreateBaseItemConfig` → `ItemConfig.ItemPrefabs`. `ItemConfig.GetPrefabForName("Player")` returns that baked entity; `PlayerDataController.SetupPlayerEntity` and `SaveGameManager` `Instantiate` it.

Consequences (validated 2026-07-04):
- A `Baker` can author a **companion entity** via `CreateAdditionalEntity(TransformUsageFlags.ManualOverride)`; it is included in the prefab's `LinkedEntityGroup`, so `Instantiate` **co-instantiates it and remaps intra-group `Entity` references per instance** (the same mechanism `ColliderParent`/`PhysicsRenderEntity`/`RenderMeshChildren` already rely on). `ManualOverride` => no auto transform components / no `Parent`, so the companion is a transform-independent root. `DestroyEntity` on the root cascades to the companion via the linked group.
- This is how the player's `PlayerSimulationObject` (spec 002, Phase 8) is now authored — see [[remote-player-presentation-position-bug]] and the `PlayerBaker` in `PlayerAuthoring.cs`. The old runtime `PlayerSimulationObjectLifecycleSystem` was **deleted** (production creates the sim-object only via baking; EditMode tests build it with a helper that mirrors `PlayerBaker`). Because the sim-object is `[Save]`-free but the player's OLD saved `KnnFleetEntity` (`[Save]`) would be re-added on load (SaveGameManager re-adds every saved component onto the fresh prefab-instantiated entity), the runtime move's implicit save cleanup was replaced by upgrade `Step0_50_0_1`, which strips `KnnFleetEntity` from saved *player* entities (keyed on presence of a `Player` component, so construction bots etc. keep theirs). All affected saves are `< 0.50.0.1` (feature unreleased), so that existing step covers them — no version bump.

Verify baked prefabs WITHOUT a full menu-driven game: in play mode, `execute_code` → get `ItemConfig` singleton (`CreateEntityQuery(typeof(FFCore.Config.ItemConfig)).GetSingleton(...)`), `GetPrefabForName("Player")`, `em.Instantiate(prefab)`, assert the instance's refs remap to itself (not the prefab), then `em.DestroyEntity(inst)`. The baked prefab entity itself is queryable with `EntityQueryOptions.IncludePrefab | IncludeDisabledEntities`. (First-play Burst compile after a full reimport can push the play-mode boot to 5+ min; the game may sit at the menu with no live player, so instantiate-from-ItemConfig is more reliable than waiting for a spawned player.)
