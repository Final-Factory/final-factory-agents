---
name: elapsedgametime-is-the-per-peer-wall-clock
description: "`FinalFactorySystemBase.ElapsedGameTime` (FinalFactorySystemBase.cs:67) returns `FFTimeData.realElapsedTime`, the per-peer WALL clock that FFTimeData.cs:11-20 says forks lockstep peers -- seven fixed-group systems roll RNG or timers from it (CometSpawner, CosmicObjectRevealer, AutoRotator, LogisticsStation, OrphanedShip, TeslaArcAnimation, LogisticsBayAnimator), and CometSpawnerSystem was caught live spawning a comet on one peer only (073 g5d). Simulation code uses `simulationElapsedTime`; a `GetRandomForEntity(..., entity)` roll is per-peer too because the Entity index is a per-World allocation artifact."
---

# `ElapsedGameTime` is the per-peer wall clock (073, 2026-09-16)

**The trap.** `FFTimeData` has two clocks: `simulationElapsedTime` (deterministic, host-authored, serialized —
"simulation code that needs elapsed time MUST use this", `FFTimeData.cs:16-20`) and `realElapsedTime`
("per-peer wall time, forks lockstep peers", `:11-14`; advanced by engine `DeltaTime` in `TimeSystem.cs:176`).
The convenience property every `FinalFactorySystemBase` inherits, `ElapsedGameTime`, returns the WRONG one
(`FinalFactorySystemBase.cs:67`). Nothing in the name says so.

**Proven live.** `CometSpawnerSystem` (`FFFixedEarlyGroup`, `CometSpawnerSystem.cs:46,67`) rolls
`RandomSystem.GetRandom(MasterSeed, ElapsedGameTime)`; on a Mac host <-> Windows client pair the `census`
fingerprint showed a `[LinearMotion, Comet]` entity on the CLIENT only (g5d epoch 1 hb 1841 -> verdict
1848). A comet lands as a mineable Comet Fragment (`Placeable`), so the peers' worlds diverge for good;
the file's own comment (`:33-37`) calls comets "wall-clock RNG … different heartbeats per run/peer".

**Census (scout, 2026-09-16, scope Assets/Scripts/FFSystems, 427 files).** Class A = fixed group,
simulation-visible: `CometSpawnerSystem.cs:46,67`; `CosmicObjectRevealerSystem.cs:114,150` (also
positions the PLAYER revealer from `LocalToWorld` = presentation, and keys its 5% sample on the Entity
index; adds `[Save]`d `FogObserver` on different heartbeats per peer — live g5d hb 899);
`AutoRotatorSystem.cs:24,53-56`; `LogisticsStationSystem.cs:52,89` (its own comment: "either one
desyncs Health across peers"); `OrphanedShipSystem.cs:64,155`; `TeslaArcAnimationSystem.cs:28,42`;
`LogisticsBayAnimatorSystem.cs:23,55` (`SystemAPI.Time.ElapsedTime`). Class B (fixed group,
telemetry-only, documented): `MiningStationProductionBonusSystem.cs:95,167`,
`TerrainExtractorMinerStateSystem.cs:82`, `DeathSystem.cs:100,228`. Correct examples:
`UnitOverlapPreventionSystem.cs:96,117`, `EnemyCampBuilderSystem.cs:72,201` (`simulationElapsedTime`).

**Rules.** In a fixed group never read `ElapsedGameTime`/`realElapsedTime`/`SystemAPI.Time.*` for
anything simulation-visible; use `simulationElapsedTime` (and `FFTimeData.deltaTime`,
[[fixed-group-engine-time-reads-are-frame-rate-desyncs]]). Never seed a lockstep roll with an `Entity`
([[ecs-iteration-order-is-archetype-creation-order]]). Never position a player-range decision from
`LocalToWorld` ([[player-presentation-transform-forks-combat]]). Tracking: 073 T022/T023.
