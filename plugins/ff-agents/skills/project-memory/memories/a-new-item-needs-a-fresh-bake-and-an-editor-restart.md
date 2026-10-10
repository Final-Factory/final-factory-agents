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

**Also.** A player build bakes at build time from the same assets, so it is right whenever the editor was.
