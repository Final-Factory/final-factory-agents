---
name: fixed-group-reads-of-localtoworld-are-frame-count-bugs
description: A heartbeat-cadenced system that reads LocalToWorld (or any component only a per-engine-frame system writes) has a frame-count dependence — derive the value the per-frame writer would produce instead
metadata:
  type: project
---

`LocalToWorld` is **never written by simulation**. `LocalToFFWorldSystem` composes it from
`LocalTransform` in `TransformSystemGroup` (`LocalToFFWorldSystem.cs:38`), which runs once per
ENGINE FRAME. So any heartbeat-cadenced reader gets a value whose freshness depends on how many
non-heartbeat frames happened to elapse — wall clock, which two peers at different frame rates
answer differently. **That is a desync, not an inaccuracy.**

The same argument applies to any component whose only writer runs on the presentation/controller
cadence. `LocalToWorld` is the worst case because it is also presentation-TOUCHED: the render
bracket overwrites it with a smoothed matrix every frame and restores it at
`InitializationSystemGroup`/`OrderFirst` (`WorldEntityInterpolationRenderSystem.cs:30-38`).
Authoritative `LocalTransform` is never written there.

**Real incident (055 R37, fixed at game-repo `7304103d6`).** `KnnSystem` gathered its KD-tree
source and viewer positions from `LocalToWorld` while running in `FFFixedEarlyGroup`, `OrderFirst`
— ahead of the transform pass in the same frame. `AttackingShipSpawnerSystem` is `FFFixedLateGroup`
(`:51`) and writes the spawn pose as `LocalTransform` only (`:149-152`), so a camp wave entered the
tree at the PREFAB's baked matrix on whichever peer got no intervening frame. Measured on BEAST:
epoch 1 heartbeat 1289, host build pose FC23558D vs client 10BEF1A0 on three co-located camp
guards, under an EQUAL end-of-heartbeat roster pose — the end-of-heartbeat fingerprint agreed
because it reads AFTER the transform pass healed it, which is why this hid for so long.
`LegacyKnnLoadPathWarmup.cs:95-101` had already named the identical class for the load path and
fixed it by writing the matrix itself; the spawn path had no such fix.

**How to apply.**

1. Fix it at the READER, not the writer. Per-writer fixes have to be remembered by every future
   writer; a reader that derives the value is safe by construction. R37's shape:
   `Assets/Scripts/FFSystems/Knn/KnnChunkPoses.cs` — every KNN job now composes the pose the
   transform pass WOULD have written.
2. Reproduce the per-frame writer's rule EXACTLY, exclusions included, or the reader and the
   writer can disagree. For `LocalToWorld` that means: compose `PostTransformMatrix` when present
   (it can carry a translation), and fall back to reading `LocalToWorld` for an entity with a
   `Parent` (the world pose is the parent chain's) or with a `[WriteGroup(typeof(LocalToWorld))]`
   component — `Unity.Physics.GraphicsIntegration.PhysicsGraphicalSmoothing` is the only one in
   the package set, and `LocalToFFWorldSystem`'s own query excludes both
   (`LocalToFFWorldSystem.cs:184-189`).
3. Argue the blast radius before you land it. Where the pass HAS run,
   `LocalToWorld.Position` is bit-for-bit `LocalTransform.Position` (`ToMatrix()` puts it in the
   translation column verbatim), so the value changes ONLY in the frame-count-dependent case. That
   is what makes this a bug fix rather than a trajectory shift, and it is worth stating in the
   commit — the previous KNN input fix (R35) DID move every ship and needed Ben's eyes.
4. Do the sweep before claiming "no presentation reads simulation": list every writer of the
   component by cadence. In this repo the per-frame `LocalTransform` writers are
   `LocalPlayerMotionSystem`, `RemotePlayerLinearMotionPresentationSystem`, `CameraFollowSystem`
   and `WarningIconIndicatorSystem` — none touches a KNN entity, because the player entity carries
   no KNN component (`PlayerAuthoring.cs:193-200`); the player's participation lives on the
   heartbeat-driven `PlayerSimulationObject` (`PlayerSimulationObject.cs:79-83`).

Sibling classes: [[055-liveness-and-comparison-surface-lessons]] (the R34b/R35 KD-tree INPUT-ORDER
fork — same system, different input property) and
[[join-load-route-provisioning-desync-class]] (R30's cold INPUT, which is this class restricted to
the load route).
