---
name: short-circuit-hoist-unguards-lookup
description: Hoisting a read out of a && short-circuit silently removes the guard it depended on — a ComponentLookup indexer that was safe because of evaluation order becomes unguarded
metadata:
  type: project
---

A `ComponentLookup`/lookup indexer read that is only safe because it sits on the right-hand side
of `condition && lookup[entity].Field` depends on short-circuit evaluation order for its safety —
moving that read out to a separate statement above the `&&` (e.g. during a refactor to cache the
value) silently drops the guard, and the indexer now throws on entities that fail `condition`.

**Real incident**: T044j → `WanderSystem` crashed on `AncientGuardian` entities this way — the
guard-then-read pattern looked like redundant code and got hoisted, removing the only thing
stopping the lookup from firing on entities without the component.

**How to apply:** before hoisting any read out of a `&&`/`||` chain, check whether the
short-circuit was load-bearing (a null/missing-component guard), not just style. If it is, keep
the read inside the conditional or add an explicit guard at the new call site.
