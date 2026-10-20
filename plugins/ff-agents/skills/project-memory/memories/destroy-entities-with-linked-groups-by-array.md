---
name: destroy-entities-with-linked-groups-by-array
description: EntityManager.DestroyEntity(EntityQuery) throws on entities whose LinkedEntityGroup reaches outside the query (Burst aborts a player); destroy by ToEntityArray, and match references against the dropped set, not em.Exists
metadata:
  type: project
---

**w1590, 2026-10-20 (the bench's `-ffBenchDropShellBots`, `ContentShaderBench.DysonClips.cs` `DropShellBots`).**

- `EntityManager.DestroyEntity(EntityQuery)` throws `ArgumentException` when a matched entity's `LinkedEntityGroup` names
  entities the query does not match (an orbiting Dyson bot's render children). In a built player Burst turns it into an
  abort with no managed stack. `DestroyEntity(query.ToEntityArray(Allocator.Temp))` destroys each root with its whole
  linked group and works.
- Right after that destroy, `em.Exists(root)` still answered true for the dropped roots (0 of 19,123 references
  removed; the cause was not traced, cleanup components are a guess). To drop the references other entities hold (the
  platforms' `[Save]` `OwnedShip` buffers), put the roots in a `NativeHashSet<Entity>` before destroying and remove the
  entries found in it.
- A dead `OwnedShip` entry is not harmless: `ExecuteShipSpawnCommandSystem` calls `GetComponentSafeWithWarning` on each
  entry every heartbeat, about 100k warnings a run, which drowns a bench leg's timing.

Related: [[ecs-exception-class-matching]], [[bench-runs-on-a-shared-machine]].
