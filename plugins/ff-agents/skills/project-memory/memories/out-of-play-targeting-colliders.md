# Out-of-play colliders can fork targeting during placement

If placement changes enemy chase/return markers on only the placing peer, inspect the
consumed targeting ray before changing construction or excluding the census signature.

Feature074 T60 (2026-09-21) placed a Dark Star Gate at HB411. At HB412, the same actor,
target and ray endpoints produced zero host hits but two M3 gate-root hits. Both roots
had `OutOfPlay`; `TargetingSystem.TargeterJob.HasLineOfSight` treated them as blockers,
cleared the target, and `ChaseSystem.Execute` sent the wanderer home. M5 and BEAST agreed.
This differs from the ray-order bug: the hit multisets themselves differ.

`TargetingSystem` records actual consumed hits under `ShipCombatPipelineDetail` as
`TargetingDecisionTrace`; it never recasts the ray for diagnosis. Endpoint flags include
OutOfPlay=32. Pair this with a short `MoversDetail` window to identify the first changed
actor. T60 captured 12 heartbeats with no omissions in about 56 MB on the host; broad mover
captures had previously filled M3's disk. Join the investigated client last so its anchor
matches the host's final shared epoch.

Repair `1e45d7347` ignores resolved out-of-play hits, including `ColliderParent` children;
completed structures still obstruct. This matches `ProjectilePhysicsCollisionSystem.Execute`'s
existing exclusion. `CombatTargetingTest.LineOfSight_UnbuiltGateDoesNotOccludeButBuiltGateDoes`
replays the observed fraction and checks obstruction returns when OutOfPlay is removed.
Both cases failed before the fix, then passed; live acceptance must still run on all machines.
