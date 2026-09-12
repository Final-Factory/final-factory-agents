---
name: objective-code-runs-per-peer-use-the-op-queue
description: "Tutorial/objective code (triggers, OnStart actions, completion rewards) runs per peer on engine frames; any simulation write there must ride the ordered op queue as a host-authored outbound op, or the peers diverge by exactly one heartbeat (run-2 vision fork at hb 7936, fixed by ops 58/59 in ae0623198)."
---

# Objective code runs per peer — simulation writes must ride the op queue (2026-09-11, 069)

**The defect shape.** `SpawnEnemyCampTrigger.PerformActionImpl` (the `7_DestroyEnemyCamp.asset`
OnStart trigger) created the tutorial's Urso spawner straight into the ECS world on whichever
peer's `ObjectivesController` started objective 7, and `ObjectivesController.CompleteObjectiveNoCleanup`
wrote the objective research reward into the host player's `[Save]` `ResearchPointsTracker` on
every peer. Objective 6 is a tracker-counter objective the client completes on the projection RPC,
so the client started objective 7 one heartbeat after the host: `SpawnerArmDetail` total 91→92 at
hb 7935 on the host, hb 7936 on the client → a `vision`-only verdict for ONE heartbeat at epoch 1
hb 7936, then agreement again. A one-heartbeat, self-healing fork whose site is an objective
boundary is this class.

**The rule (022 D1 addendum).** Objective/tutorial code runs on engine frames, per peer, off the
`ObjectivesController` — it is presentation-cadence. Anything it does to simulation state must be
host-authored and applied on a heartbeat boundary on every peer: an outbound-only op
(`AuthoritativeOperationBroadcast`) that the client side no-ops. Fix `ae0623198`: ops 58
`ObjectiveEnemyCampSpawn` + 59 `ObjectiveResearchReward`; trigger + reward callers go through
`ObjectiveSimulationAuthoring` (client = no-op); `ResearchController.ApplyResearchPointsToTrackerLocally`
is reserved for the apply leg. Tests `ObjectiveOperationsTest` (8).

**How to apply.** Before adding any objective trigger/reward/verifier side effect, grep it for
entity creation, `[Save]` component writes, or RNG draws; route them through the
`add-network-operation` recipe. Audit tell: a single-heartbeat verdict on `vision`/spawner
fields coinciding with an objective transition. Reports: 069 plan, 23:20 UTC PROGRESS block.
