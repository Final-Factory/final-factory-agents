---
name: blockallocator-budget-crash
description: "Root cause of \"Cannot exceed budget of 16777216 in BlockAllocator\" — archetype explosion from one-at-a-time AddComponent in save-load; which 16MB allocators exist and what actually grows them"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 6ac54f46-7a42-48f2-a8d8-cf8664883f8b
---

Unity Entities has TWO fixed 16MB BlockAllocators per World, either can throw
"Cannot exceed budget of 16777216 in BlockAllocator":
- `EntityComponentStore.m_ArchetypeChunkAllocator` — archetype metadata (~1-3KB per archetype, never freed).
- `EntityQueryManager.m_EntityQueryDataChunkAllocator` — query data + one `MatchingArchetype`
  record per (queryData × matching archetype), never freed. With this project's hundreds of
  queries, each new archetype costs several KB here; this one usually blows first.

Key facts (verified in package source `com.unity.entities@95352e4aa61e`):
- `CreateEntityQuery` DEDUPES `EntityQueryData` by desc hash — repeated identical descs do NOT
  grow the 16MB budget. They DO leak a ~sizeof(EntityQueryImpl) persistent malloc per call if
  never Disposed (slow generic leak, not this crash).
- Archetypes are permanent for the World's life; the real driver is distinct-archetype count.
- `ComponentTypeSet` holds max 15 types (FixedList64Bytes).

The 2026-07 player crash: `SaveGameManager.RecreateEntities` added saved components to 32k
entities one `AddComponent` at a time → every intermediate component combination became a
permanent archetype → budget exhausted at/shortly after load. Fix: batch missing types into
`AddComponent(entity, ComponentTypeSet)` chunks of ≤15.

Watch for the same pattern in any deserialization/copy loop (`SerializationUtil` has a
similar one-at-a-time copy path, bounded in practice).

## 2026-10-01: the live crashes were play-driven, and the stores are now 256 MB (w169, #887)

- 0.50.0.58 (Windows host, 2 h 24 min) and 0.50.0.61 (macOS client, 3 h 38 min) both died in
  `EntityComponentStore.CreateArchetype` under an ECB playback, at about 10,200 archetypes. The
  archetype store went first there, not the query store.
- Growth follows minutes of play, not loads: 20 to 60 new archetypes a minute in a developed world
  (190 a minute in the first quarter hour of one session); a reload alone adds about 10. The census
  is only logged on save and load, which makes the growth look tied to loads. Count the
  `[MP pacing]` windows between two `[Archetypes]` lines before blaming a join or a recovery.
- The multipliers are add/remove tags used as state. Health bars are the largest (`Child`,
  `HealthBarInitializer`, `HealthBarReference`: up to five extra archetypes per damaged entity
  kind). Plan: `Documentation/Archetype-Growth-Plan.md` (PR #892).
- **Hotfix:** `Assets/Scripts/EntitiesInternals/` (an `.asmref` into `Unity.Entities`) swaps both
  stores for 256 MB ones on `DefaultWorldInitialization.DefaultWorldInitialized` and logs
  `[ArchetypeStoreBudget] World '...': archetype store 16 MB -> 256 MB, query store 16 MB -> 256 MB`.
  Safe because Entities only allocates from them and never frees one allocation. Its README lists
  what to re-check on an Entities upgrade. The `[Archetypes]` line now carries
  `archetypeStore=used/budgetMB queryStore=used/budgetMB`.
- **Proof in a built player:** `ffauto:archetypes.stress|20000` (DevOnly), in steps of 2,500 so the
  host never stalls long. 21,805 archetypes read 26.1 MB of archetype store and 12.1 MB of query
  store on Windows and macOS: the query store is the second cliff, so both must be raised.
- The `.ips` of a macOS Burst abort names an unrelated thread as crashed (a helper waiting on a
  semaphore); the real stack is thread 0 and matches the tail of `Player.log`.
