---
name: ecs-exception-class-matching
description: Match the exception CLASS to the API before theorizing about an ECS crash — ECB missing-buffer vs missing-component throw different exception types
metadata:
  type: project
---

Two ECS "missing X" failures throw DIFFERENT exception classes — read the class before guessing
the cause:

- An `EntityCommandBuffer` append (`AppendToBuffer`, `SetBuffer`, etc.) on an entity that lacks
  the target buffer type throws `InvalidOperationException: "Buffer does not exist"`.
- `SetComponent`/`GetComponentData`, or a `ComponentLookup` indexer, on an entity that lacks the
  component throws `ArgumentException` (stack shows `AppendRemovedComponentRecordError` or
  similar internal EntityManager machinery).

**How to apply:** when triaging a crash stack, check which exception class it is FIRST — it
narrows the guilty API family (ECB buffer op vs direct component read/write) before you go
looking at the calling system's logic.
