---
name: elapsedgametime-is-the-per-peer-wall-clock
description: "`FinalFactorySystemBase.ElapsedGameTime` was the per-peer WALL clock (`FFTimeData.realElapsedTime`) under a name that did not say so; it is now an `[Obsolete]` alias kept only for the mod template, and two explicit properties replaced it -- `SimulationElapsedTime` (deterministic `simulationElapsedTime`, every simulation read) and `WallClockElapsedTime` (telemetry only). The comet spawner it fed forked a live Mac<->Windows pair TWICE over: the roll seed AND the targeted player (an index into the player query's entity order, a per-World allocation history). Never read the wall clock, an Entity handle or a query's entity order in a fixed-group decision; the full reader census lives in Documentation/RealElapsedTime-Determinism-Audit.md."
---

# `ElapsedGameTime` was the per-peer wall clock (073 T022, 2026-09-16)

**The trap.** `FFTimeData` has two clocks: `simulationElapsedTime` (deterministic, host-authored, serialized —
"simulation code that needs elapsed time MUST use this", `FFTimeData.cs:16-20`) and `realElapsedTime`
("per-peer wall time, forks lockstep peers", `:11-14`; advanced by engine `DeltaTime` in `TimeSystem.cs:176`).
The convenience property every `FinalFactorySystemBase` inherited, `ElapsedGameTime`, returned the WRONG one
(`FinalFactorySystemBase.cs:67`) and nothing in the name said so.

**Resolution (commit `8c2e7f900`).** `FinalFactorySystemBase` now exposes `SimulationElapsedTime` and
`WallClockElapsedTime`; `ElapsedGameTime` stays as an `[Obsolete]` alias of the wall clock ONLY because the
shipped mod template compiles against it (`FinalFactoryModTemplate/Assets/Scripts/Systems/FleetRandomMovementSystem.cs:36`;
mods build against shipped DLLs, so a removal breaks every mod at the next build — switch the template to
`SimulationElapsedTime` only after a build carrying it ships). Nothing in `Assets/Scripts` reads
`ElapsedGameTime` any more. Its three callers were `CometSpawnerSystem` (→ simulation clock),
`AutoRotatorSystem` (→ simulation clock; heartbeat-cadence decoration, rotation is not fingerprinted) and
`DeathSystem` (→ WALL clock: its `Stat.TimeStamp` feeds the wall-clock-bucketed stats UI,
`ProductionStatsResetSystem.cs:34`). Do not make the property a silent semantic swap — telemetry must keep
the wall clock.

**Two per-peer inputs, not one.** `CometSpawnerSystem` also picked the targeted player by index into
`AllPlayersForJob()`'s `ToEntityArray` — chunk/archetype order, i.e. each World's allocation history (the
local player's archetype differs from a remote one's; a joined peer allocates players in another order).
Fixed with a `Player.Guid`-sorted list (`SharedOracleUpgrades.cs:46` precedent). `CometSpawnDeterminismTest`
pins both: RED on the old code was first spawn hb 642 vs 274 (wall clock) and target `(6000,…,1000)` vs
`(1000,…,6000)` (entity order). The comet itself is a FLYBY (`Assets/Prefabs/Comet.prefab` = Comet +
LimitedLifetime 60 s + LinearMotion) — it never lands; fragments are map generation.

**Full-scope census (2026-09-16, `Assets/Scripts`, tests excluded; the earlier scout census was
FFSystems-only).** Fixed-group simulation-visible: `CosmicObjectRevealerSystem` (073 T023, fixed the same
day: player revealer from `Player.SimulationPosition`, placed revealer sampled by
`GetRandomForTileAndSimulationTime(Seed, CenterTile, simTime)`), `OrphanedShipSystem:64,155` (open, 073
T026: every peer rolls and appends a `ShipSpawnCommand` to its OWN MePlayer). Fleet-lane by documented
design: `LogisticsStationSystem:89`. Presentation-on-heartbeat: `TeslaArcAnimationSystem:28`,
`LogisticsBayAnimatorSystem:23`. Telemetry: `MiningStationProductionBonusSystem:95`,
`TerrainExtractorMinerStateSystem:82`, `DysonProductGeneratorSystem:62`, `ProductionStatsResetSystem:34`.
Host-baked / single-player only (safe by pattern): `CompleteMiningRequestNetworkOperation:209` (host resolves
the seed once, before the broadcast), `MiningAction:558,583` (the `!IsConnected` branch). Canonical record:
`Documentation/RealElapsedTime-Determinism-Audit.md` (2026-09-16 section).

**Rules.** In a fixed group never read `ElapsedGameTime`/`realElapsedTime`/`SystemAPI.Time.*` for anything
simulation-visible; use `SimulationElapsedTime` (and `FFTimeData.deltaTime`,
[[fixed-group-engine-time-reads-are-frame-rate-desyncs]]). Never seed a lockstep roll with an `Entity`, and
never index a decision by a query's entity order ([[ecs-iteration-order-is-archetype-creation-order]]) — sort
by a replicated identity first. Never position a player-range decision from `LocalToWorld`
([[player-presentation-transform-forks-combat]]).
