---
name: test-the-real-entity-shape-not-a-hand-built-fixture
description: "A fix and its test both encoded a wrong guess about an entity's components, so the test passed and the game broke: the Ancient Treasure Take All fix (c36adc2b9) keyed on 'no Placeable', LootBox.prefab HAS one, every real treasure became unlootable (fixed b38a4680a). Read the real prefab or the live entity first, build fixtures to that shape through the real entry point, and verify once on a prefab-instantiated entity in a loaded save before calling it done."
metadata:
  type: feedback
---

# Test the real entity shape, not a hand-built fixture (live MP, 2026-09-22)

**What happened.** Routing a loot box's "Take All" through the InventoryTransfer op (c36adc2b9),
the dispatcher used the new lootable endpoint only for entities with NO `Placeable`, on the guess
that loot boxes are not grid structures. `Assets/Resources/ItemEntities/LootBox.prefab` carries
`PlaceableAuthoring`, but nothing registers a loot box in the grid map. So every real treasure took
the tile path, and the host rejected the unresolvable tile. That reject is trace-level, so nothing
was logged and "Take All does nothing" was the only symptom. The unit test passed because it
hand-built a box WITHOUT a `Placeable`: it tested the guess, not the game. Ben found it in minutes
of play. Fixed in b38a4680a: anything with `DestroyWhenLootedMarker` takes the lootable endpoint.

**Rules.**
1. Before a fix or a test depends on which components an entity has, check the real thing. Either
   resolve the prefab's `m_Script` guids to their `*Authoring.cs` (grep the guid in `*.cs.meta`),
   or dump `EntityManager.GetComponentTypes` on a live instance in the editor.
2. Build test fixtures to that real shape, and drive the real entry point (the dispatcher or panel
   code path), not a hand-filled op payload that skips the decision under test.
3. Before calling a gameplay fix done, verify it once on a real entity. Load a save in the editor,
   `em.Instantiate(ItemConfig.ItemPrefabs[id])`, run the exact UI code path, pump
   `EditorApplication.Step()`, and assert the outcome. For the treasure: artifact 0 -> 1 in the
   player's inventory and the box destroyed, in about five short `execute_code` calls.
4. After a local mutation becomes a request/apply op, a host-side reject makes "nothing happens"
   the only symptom. Only an end-to-end check catches it. See
   [[silent-host-rejects-look-like-a-dead-ability]].

Related: [[audit-fixture-and-report-grounding]] (inspect the baked `ItemPrefabs` component matrix
before blaming a loader).
