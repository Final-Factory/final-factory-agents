---
name: a-new-item-needs-a-fresh-bake-and-an-editor-restart
description: "After adding Resources item or weapon assets the editor boots to 'Something went wrong with game initialization' (ArgumentOutOfRangeException, StartController.cs:322): the entity prefab container is baked from Resources.LoadAll, which Unity does not track, and a long-lived import worker keeps a stale view of Resources even after a forced bake; restart the editor, then touch FFComponents code so the bake runs with the new worker. The baker logs its item-config count."
---

# A new item or weapon needs a fresh bake, and sometimes an editor restart (2026-10-09, w809)

**Symptom.** After adding item configs (`Assets/Resources/ItemConfig`) or weapon configs, play mode (or a
player) logs `Something went wrong with game initialization in the Start Controller` with an
`ArgumentOutOfRangeException` at `StartController.cs:322` (`itemPrefabList[index + 1]`): the baked
`FfItemEntityPrefab` list is shorter than `Resources.LoadAll("ItemConfig")`.

**Cause.** `EntityPrefabContainerBaker` reads `Resources.LoadAll`, and Unity tracks no dependency on that call,
so a new asset changes nothing the subscene depends on and the old bake is reused. Re-importing
`EntitySubScene.unity` does not rebake (a DefaultImporter, about 1 ms). A code change in `FFComponents` does
(the baker's assembly is part of the artifact's key), but the bake runs in an asset-import worker, and a worker
that was alive when the assets were created kept a stale view of the Resources folders: the forced bake still
saw 200 of 201 configs. A new worker saw all 201.

**Fix that worked (w809).** `mcp__machine__unity restart` (fresh workers), then edit anything in `FFComponents`
(the baker now logs `Baking the Entity Prefab Container: N item configs`, so the log shows N against the number
of `.asset` files in `Assets/Resources/ItemConfig`), refresh, enter play mode. Compare N with the file count
before trusting a boot.

**Also seen (2026-10-11, w1046).** After the restart, forcing the entity scenes' global dependency also rebaked the container in a running editor: `execute_code` finding `Unity.Scenes.EntitiesCacheUtility` (assembly `Unity.Scenes.Editor`) and invoking its static `UpdateEntitySceneGlobalDependency` by reflection, then entering play mode (the bake logged 202 configs against 202 files). The same call rebakes after editing an item's variant list (Art Variants, FinalFactory #1515).

**Also seen (2026-10-25, w2130): a player build dies in the entity-scene step.** `scripts/nightly/build_player.sh` failed with `Dynamic array capacity overflow: 0xffffffffff03f208`, then `Size overflow in allocator`, in `EntitySceneBuildUtility.PrepareAdditionalFiles` / `CalculateCustomDependencyData`. Two lothdesktop sandboxes (slot1 and slot3) failed on commit f00a78d9ad with the same value while beast built that commit fine, so it is a corrupt entity-scene artifact on the machine, not the code. There was no `Library/BuildCache` or `Library/EntityScenes` to move aside. Fix: start the sandbox editor, invoke the same `UpdateEntitySceneGlobalDependency` by reflection, stop the editor, rebuild (it built, `entityFiles 1`). The call rewrites the tracked `Assets/GlobalEntitiesDependencies/GlobalEntitySceneDependency.asset` (its cacheGUID): commit that only locally for the build, never into a PR that does not want it.

**Also seen (2026-10-31, w2650): a renamed item asset.** Renaming an `ItemConfig` asset in an open editor left the bake and the runtime list disagreeing for two runs even after the reflection call: setup threw `Logistics Network Station 6 has no accepted ships: Advanced Ship Assembler` and `Failed to setup new IDs on item Advanced Solar Panel` (ids shifted under the stale bake). `mcp__machine__unity restart`, then the `UpdateEntitySceneGlobalDependency` reflection call and `AssetDatabase.Refresh()`, fixed it (the log showed the new N and `Resources.LoadAll` gave the expected order). A throwaway item experiment ends with `git checkout -- Assets/GlobalEntitiesDependencies/GlobalEntitySceneDependency.asset` (and the play-mode `.mat` churn under `Assets/Art`), or the sandbox is left dirty.

**Also.** A player build bakes at build time from the same assets, so it is right whenever the editor was.
