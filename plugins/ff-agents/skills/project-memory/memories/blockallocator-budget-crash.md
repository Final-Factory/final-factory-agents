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
