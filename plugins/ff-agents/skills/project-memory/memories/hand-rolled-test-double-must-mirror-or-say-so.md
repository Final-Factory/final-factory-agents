---
name: hand-rolled-test-double-must-mirror-or-say-so
description: A hand-rolled test double that reproduces a production shape must name the real-system test covering the actual code path, or the mirror goes vacuous when either side changes
metadata:
  type: project
---

A hand-rolled test double that deliberately reproduces a production code shape can go vacuous in
BOTH directions if it mirrors too faithfully and nothing points back at the real coverage.

**Real incident (055 R37, `Assets/Tests/Knn/KnnLateSpawnTransformPassWitnessTest.cs`).**
`KnnLateSpawnTransformPassWitnessTest`'s spawn helper deliberately reproduces
`AttackingShipSpawnerSystem`'s shape — write `LocalTransform` only, never `LocalToWorld` — and the
file's own docstring explains why (`:14-33`: "so a future spawner that writes only `LocalTransform`
is still safe"), which is legitimate: the point of the witness is that the KNN reader must be safe
for that exact writer shape. But the docstring does NOT name the real-system test that covers the
actual production code path it mirrors — `AttackShipSpawnCombatIdentityTest`
(`Assets/Tests/EnemyAttacking/AttackShipSpawnCombatIdentityTest.cs`), which drives the real spawner.
Nothing in the file tells a future reader where to look if `AttackingShipSpawnerSystem`'s shape
changes and the mirror silently goes stale — a production fix or regression on either side could
land with the witness undisturbed in either direction.

**Rule**: whenever a hand-rolled double mirrors a production shape, the comment must name the
real-system test that covers the actual code path, not just explain the mirroring choice. Same
family as the committed-golden mirror rule ([[mirror-implementation-golden-fixture]]), but for a
hand-rolled test double standing in for one system instead of a cross-language reimplementation of
the same logic — the failure mode is the same (a mirror that can silently stop meaning anything),
the mechanism differs (no shared fixture to pin agreement, so the fix is a pointer to the real
coverage instead of a golden input/output pair).
