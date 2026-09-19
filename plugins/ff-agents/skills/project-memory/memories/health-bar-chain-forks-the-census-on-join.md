---
name: health-bar-chain-forks-the-census-on-join
description: "074 T106: HealthBarInitializer/HealthBarReference/HealthBar (FFComponents.Combat, none [Save]d) exist on a peer only from the hit that peer observed, so a joining or recovered peer lacks them until its entities are hit again — census unequal for the first 6–9 hb after every join (leg t5), spurious recovery when it outlives the hb-8 sample. Fixed b577625f3 by stripping all three from the census; the single-player per-heartbeat census-dump probe that found it, and the hb-0-only load transients deliberately NOT stripped."
---

# The HUD health-bar chain forks the census after a join (074 T106, 2026-09-19)

**Signature.** A joining client's census is unequal for its first 6–9 heartbeats and then equal;
when the transient outlives the sampler's hb-8 sample the host recovers it for nothing (leg t5:
BEAST join hb 1–6 no verdict, M3 join hb 1–8 → verdict → recovery → epoch 3 unequal 1–9). All other
surfaces equal throughout; the length depends on world content.

**Mechanism.** A hit adds `HealthBarInitializer` (`IncomingHealthChangeSystem.cs:261-266`),
`HealthBarCreatorSystem` instantiates the bar prefab as a `LinkedEntityGroup` child and points
`HealthBarReference` at it (`HealthBarCreatorSystem.cs:52-71`), `HealthBarSystem` destroys both at
full health (`HealthBarSystem.cs:56-71`). None of the three is `[Save]`d and the only simulation
reader is the has-one check, so a peer that just LOADED (join, recovery) carries no bar for anyone
until that entity is hit again, while the host has carried them since the earlier hit. Fix: all three
in `CensusTypePolicy.BuildExplicitStrip` (`DeterminismStateFingerprintJobs.cs`); guard
`CensusFingerprintTest.CensusHash_IgnoresTheHealthBarChain`; three-peer-proven on leg t6 (BEAST join
epoch 1 census equal all 102 hb, M3 join epoch 2 equal all 769 hb on both pairs, 0 verdicts).

**The 10-minute probe (single-player editor, no leg).** Play → `SaveGameManager.LoadGame(
LobbyCreationParameters.SinglePlayerGame, "<the leg's checkpoint>", true)` → pump
`EditorApplication.Step()` until `GameMetaState.GameStarted && MePlayer exists && Heartbeat.
CurrentHeartbeatFrame > 40` (34 steps / 14 s on `074-p1-t4-obj6`) → reflect
`FFSystems.Multiplayer.DeterminismStateFingerprintJobs.CollectCensusRecords(EntityManager, bool
includeTypeNames)` (internal static; `CensusRecord` fields `Signature`/`Count`/`TypeNames` are
internal — reflect them too) and write one file per DISTINCT heartbeat for hb 0–11, then one at
~hb 200; diff each early dump against the late one as component-set differences (match an
early-only signature to the late-only signature sharing the most types, print the symmetric
difference). The rows that vanish by hb ~9 are the join transients. Keep every `execute_code` call
short — see [[pumped-execute-code-scripts-can-wedge-the-editor]].

**hb-0-only transients, deliberately NOT stripped** (they never reach an audit sample, which is taken
after the first heartbeat): `CompoundColliderChild` on all 236 asteroids (baked buffer, removed by
`CompoundColliderRepairSystem` in the first init group), the two `[Save]`d player-ability buffers
`PlayerAbilityFireIntent`/`PlayerAbilityCommandedShip` (absent after a load, installed at hb 1 by
`PlayerAbilityStateInstallSystem`), `SimulationPoseInitialized` (set by the first heartbeat op),
the `DeterministicSpatialSnapshotMap` singleton. Strip only what the audit can see.

Siblings: [[material-property-overrides-fork-the-census]] (T105), the T103 per-load report
singletons, [[per-peer-gates-on-structural-changes-fork-the-census]].
