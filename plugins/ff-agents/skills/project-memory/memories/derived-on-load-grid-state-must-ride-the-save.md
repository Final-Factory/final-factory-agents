---
name: derived-on-load-grid-state-must-ride-the-save
description: "A grid or map the loader RE-DERIVES from entities (FFGrid.EntityMap, like B1's WorldObjectTiles) never equals the host's live, history-dependent one; persist the ownership itself and overlay it after the regrid pass."
---

# Derived-on-load grid state must ride the save (2026-09-11, 069 B3)

**Symptom.** After a join or load the client's `FFGrid.EntityMap` held 229,096 entries against
the host's live 230,612, with EVERY fingerprint clean (rejoin10). At camp (669,0,556) 66 tiles
were host-only and 15 client-only, stable from epoch 1 heartbeat 7. Nothing folds the grid, but
`EnemyCampBuilderSystem.AreTilesOccupied` reads it, so the first builder footprint landing on
such a tile forks `camps` on one peer only — the B1 mechanism one map over.

**Mechanism.** Every load rebuilds the grid in `RecalculatePositionsOnGridSystem`, and that
derivation is not idempotent: `PlaceCircularPlaceableInGrid` skips a tile on conflict, so a
circle re-claims tiles a since-deleted occupant held when the host generated it; the irregular
asteroid bit buffer is written by `IrregularPlaceableMarshallingPrepSystem` from a
world-position origin (`tile.x - width/2`) but decoded by `IrregularTileJob` from
`Placeable.GridTile`, and its tail shift is `7 - 8 % bitIndex` (wrong operand order); and
conflicts go to whichever entity the loading world iterates first (`TryAdd`). `derive(save)`
therefore differs from the host's live grid, and differs again from `derive(save(derive(save)))`.

**Fix shape.** `EntityGridPersistenceSystem` (`ISerializableSystem` + `IBinarySerializableSystem`,
payload v1: one block per occupant — saved entity, tile-space box, bitmask over the box,
sorted; ~30 KB for 230k tiles). `DeserializeAfterEntities` runs AFTER the regrid pass
(`SaveGameManager.RecalculatePositionsOnGrid` then `SystemsDeserializeAfterEntities`), clears
the derived grid and restores the saved one through the old→new entity map; a block whose
occupant the load did not recreate is dropped whole and counted (`GridRestore` audit record). A
save without the block keeps the derived grid. Proof rejoin11: NO DIVERGENCE 1689 hb, client
`GridRestore` derived 229,096 → restored 230,612 (the host's live count), 0 dropped.

**Rule.** Any structure the loader derives that a simulation system later reads is save-worthy.
Diff the two peers' structure with an audit-detail probe (`CampOccupancyDetail`) BEFORE a
fingerprint forks; a probe over a host report that ran before the client joined must take the
host's LAST epoch-1 block (its heartbeat counter restarts at the join).
