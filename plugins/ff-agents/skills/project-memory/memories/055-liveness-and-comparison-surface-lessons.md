# 055 liveness-witness and comparison-surface lessons (R31–R34b)

**Feature:** 055 combat-mover-vision (2026-08-30, `specs/055-combat-mover-vision/tasks.md`)

Six lessons from the same feature about verification signals that need a second look before you
trust them — a liveness check declared vacuous when it wasn't, a comparison query that silently
narrowed its own population, unsaved host-only state that only forks on a reload (not a join), and
a KD-tree whose ORDER-noise looked like SET-noise. Read this alongside
[[join-load-route-provisioning-desync-class]] (arrival-route provisioning forks in the game code) —
some of these are audit/harness bugs, others are game-code bugs the audit surfaced; group-read
before trusting an exit code, a comparison surface, or a "the scenario didn't cover it" verdict.

## An exit code alone is a vacuous liveness proof; require the decline/mint audit record (R31)

A BEAST arm exiting 0 does not by itself prove a code path ran. The `economy1` run that first
reported the R30/R31 forks carried NEITHER a `LegacyProjectileMigrationDeclined` record NOR a
schema-0 projectile in that particular join snapshot — coverage of a given load-path branch is
JOIN-TIMING-DEPENDENT (whether the fixture happens to have an in-flight projectile at the exact
heartbeat a client joins). **Rule**: when a fix depends on a specific load-path branch executing,
put that branch's own audit record (decline count, mint count) in the evidence bundle — a clean
exit code proves the run finished, not that the fix was exercised.

## A liveness failure BEHIND a real divergence is unexplained, not vacuous (R31)

`enemy-camps-economy`'s `attacks`-reaches-only-1-distinct-value and `spentCamps=0` ledger checks
were provisionally filed as a "scenario just didn't run long enough" vacuity class after R30. They
were not: both were downstream of the R31 projectile-emitter allocator fork (`53113b96f`) cutting
every run short via repeated 019-recovery re-serves. Once the fork was fixed, the same fixture ran
1616 heartbeats instead of ~30, `attacks` reached 3 distinct values, and both ledgers reached
`spentCamps=2` — the category retired itself. **Rule**: don't retire a "liveness/scenario-coverage"
failure category as expected/inherent scenario weakness while an unrelated divergence is still open
in the same run. Fix the divergence first, re-measure, and only then judge whether the liveness gap
is real.

## Liveness-witness dwells must anchor on HEARTBEATS, not wall-clock (R32)

`enemy-camps-economy` is fully deterministic on BEAST (932/932 shared heartbeats byte-identical at
`53113b96f`) but was exiting 5 on liveness alone. `HeartbeatSystem.PerformQueuedOperations`
(`HeartbeatSystem.cs:581`) applies AT MOST ONE heartbeat per engine frame and returns immediately
after applying one — so a peer's achievable UPS is capped by its engine FPS, not the nominal 16
UPS tick rate. BEAST's built host frame runs 86–108 ms (≈9.3–11.6 FPS), spending essentially every
frame on a heartbeat (1.00 frames/hb), against ~16.14 UPS on a fast Mac. A witness/dwell window
sized in WALL-CLOCK seconds and calibrated against a fast machine will never fire on a slow one even
though the simulation is converged. Fix: size dwell/ceiling windows (`PostConnectDelayHeartbeats`
and siblings) in heartbeats, with wall-clock only as a loud-warning ceiling, not the primary gate.

## Comparison queries must carry the SAME EntityQueryOptions as their producers (R34, `fe6fa6bf0`)

`DeterminismStateFingerprintJobs.MoverRailQueryDesc()`/`C3VisionQueryDesc()` had no `Options` set,
so `EntityQueryOptions.Default` silently excluded every `Disabled` entity from the `movers`/`vision`
comparison surfaces — while every system that WRITES those populations declares
`IncludeDisabledEntities`: `CombatMoverRailProvisioningSystem.cs:375` installs rails on disabled
movers, `C3VisionProvisioningSystem.cs:98-125` provisions disabled holders, and
`CombatMoverRailMirrorSystem.cs:99-106` re-mirrors every disabled rail from its float record EVERY
heartbeat specifically so a re-enabled ship's rail is bit-identical across peers. That guarantee was
unobservable by construction: a docked/disabled ship's state could diverge for as long as it stayed
disabled with every compared surface reporting green, and only fork visibly at the heartbeat that
re-enabled it. **Rule**: whenever you add or audit a comparison-surface query
(`DeterminismStateFingerprintJobs.*QueryDesc`), grep every system that WRITES the same component set
for its `EntityQueryOptions` and match it — a narrower default on the READ side is a blind spot, not
a filter.

## Host-only unsaved state forks every remote apply, not just joins (R33, `8ce4c8e0b`)

`[Save]` gaps don't only bite a fresh JOIN — they bite any peer that WIPES AND RELOADS while another
peer holds continuous in-memory state, e.g. the 019 recovery cycle re-serving after a detected fork.
Two gaps found this way: `AutomationPlayerInvulnerable` (a bare zero-size ECS tag component — `[Save]`
on a zero-size type is a silent no-op without an explicit byte to persist, since
`ColumnarWorldCapture.cs:126` skips any type with `info.ElementSize == 0` when building the saved-type
table) and `HealthRegenData.Timer`. **Rule**: a round-trip save test must capture via
`MarshallingSystem.GetAllComponentTypes` (the actual `[Save]`-tagged set the game uses), never a
hand-maintained type list — a hand-listed set proves nothing about what `[Save]` really covers, and a
zero-size tag needs a real byte field before `[Save]` does anything for it at all.

## Archetype-creation-ordered KD-tree input makes neighbour SETS order-dependent (R34b, `6192ea930`)

`KnnSystem.CreateEntityQuery` (`KnnSystem.cs:257-261`) orders its source points by archetype creation
order, which can differ between peers on a tie heartbeat — not just reordering the neighbour LIST but
changing which entities land inside a fixed-K neighbour SET when a distance tie falls right at the
cutoff. `UnitOverlapPreventionSystem.cs:152` (`if (visions.Count <= 1) { linearMotion.KnnCollisionForce
= 0; return; }`) then turns one flipped tie into a WHOLE MISSING repel force for that ship, not a
small numeric drift — a single-neighbour early-out amplifies a one-entry set difference into a
binary present/absent divergence. **Instrumentation technique** (reusable beyond KNN): split every
neighbour/topology digest into an ORDER variant (hashes the sequence) and a SET variant (hashes the
sorted/unordered content). Order-noise is a constant background signal on any archetype-ordered query
and will fire on nearly every heartbeat; SET-noise — a genuinely different neighbour SET, not just a
reshuffled one — is what actually predicts a fork. Diffing only the combined digest conflates the two
and hides the signal in the noise.
