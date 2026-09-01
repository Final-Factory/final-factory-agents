# 055 liveness-witness and comparison-surface lessons (R31–R37)

**Feature:** 055 combat-mover-vision (2026-08-30/31, `specs/055-combat-mover-vision/tasks.md`)

Thirteen lessons from the same feature about verification signals that need a second look before you
trust them — a liveness check declared vacuous when it wasn't, a comparison query that silently
narrowed its own population, unsaved host-only state that only forks on a reload (not a join), a
KD-tree whose ORDER-noise looked like SET-noise, and — once that fork was diagnosed — the R35 fix,
the four verification lessons that came with it, and (R36/R37) an instrument that turned out to be
watching the wrong moment in the heartbeat. Read this alongside
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

## Close an archetype-order fork at the BUILD input, not by serializing the hot job (R35, `c84065bd7`)

`KnnSourceOrder.cs` (`Assets/Scripts/FFComponents/Knn/KnnSourceOrder.cs`) fixes the R34b fork with a
canonical 256-bit key (`KnnSourceOrderKey`, four `ulong` words, `KnnSourceOrder.cs:68-73`) over
simulation identity: tier 1 `DeterministicCombatObjectId`, tier 2 `PendingCombatIdentity` birth
provenance, tier 3 `(Placeable.ItemIdentifier, GridTile)`, tier 4 a raw-pose fallback. `KnnSystem.cs:488`'s
`SortSourcesJob` (a bounded ~255-element **serial** `IJob`, not `IJobParallelFor`) sorts the gathered
sources by this key before the tree build; `UnitOverlapPreventionSystem.cs:191` then sums neighbour
slots `[1, Count)` ranked by the SAME key (`KnnSourceOrder.Rank64`). Both the tree-build gather and the
repel consumer keep their existing PARALLEL schedules — the fix imposes order at the data feeding the
hot job, not inside it. **This is the positive-example half of the standing rule**: never serialize a
hot-path job to close an ordering bug; make its INPUT canonical instead.

## Name the non-injective residue of an ordering key instead of hiding it (R35)

Tier 4 of `KnnSourceOrderKey` (raw `LocalToWorld.Position` bits) is explicitly documented as NOT
injective — two sources with no identity at all at one exact pose are indistinguishable to the key.
Rather than treat this as a solved case, the audit surfaces it directly: the roster instrument reports
a `tier4Src` counter, and `KnnSourceOrderDeterminismTest.PositionOnlyTierCannotSeparateCoincidentSources`
(`Assets/Tests/Knn/KnnSourceOrderDeterminismTest.cs:383-397`) pins the residue by asserting two same-pose
position-only keys compare equal; every live fixture then asserts `tier4Src == "0"`. **Rule**: when an
ordering key still has a theoretical tie case, name that population as an explicit, asserted-empty
instrument field — don't just fix the common case and call the fork closed.

## Flip an instrument's assertion direction when its observable becomes canonical (R35)

`KnnSourceRosterInstrumentTest.SequenceDigest_FollowsTheCanonicalBuildOrderNotCreationOrder`
(`Assets/Tests/Multiplayer/KnnSourceRosterInstrumentTest.cs:161-181`) used to assert `enemySrcSeq`/
`fleetSrcSeq` DIFFERED under creation-order noise — 1605/1605 heartbeats disagreeing pre-fix, proof the
digest was watching non-canonical KD-tree build order. Post-R35 that build order IS canonical, so the
same test now asserts EQUALITY (0 differences) and treats any mismatch as a regression (either the
`tier4Src` residue firing, or a producer that reintroduced order-dependence). **Rule**: an instrument's
assertion direction is a contract about what the current implementation means — when a fix changes the
underlying invariant, re-derive and flip the assertion rather than leaving a stale "must differ" check
that now silently proves nothing.

## Forbid cross-seam key reuse even when the identity facts are identical (R35)

`CombatMoverProviderCatalogTest.C3SurfacesNeverCrossIntoTheLegacyFloatPathOrLocalToWorld`
(`Assets/Tests/Combat/CombatMoverProviderCatalogTest.cs:1636`) forbids the legacy float vision path
from naming any C3 symbol, including `DeterministicSpatialKey` — even though `KnnSourceOrder` needed to
rebuild the SAME identity facts (combat id, provenance, grid tile) that C3's key already encodes. R35
deliberately wrote a second, independent key rather than importing C3's. **Rule**: two paths needing the
same identity facts are not license to share one symbol across an architectural seam the tests
deliberately keep separate — rebuild the facts on the side that owns them.

## A hot-path perf delta smaller than run-to-run variance is only a pooled-statistic claim (R35)

R35's KnnSystem cost increase — **+0.011 ms/hb mean (+8.3%), +0.014 ms median (+10.8%)** — was measured
over 300 warm-up + 600 timed heartbeats × 5 passes = 3000 timed samples per side, Burst confirmed on
(`BurstCompiler.IsEnabled=True`), at a fixed census (`specs/055-combat-mover-vision/tasks.md:5533-5541`).
**Rule**: at this scale a single before/after run is noise — only report a hot-path delta this small
when it's a pooled statistic across many timed samples, not a one-shot comparison.

## An end-of-heartbeat instrument cannot adjudicate a mid-heartbeat consumer (R36, `8dfeb1d1e`)

`DeterminismStateFingerprintSystem` is `FFFixedPostTransformGroup`, `OrderLast`; `KnnSystem` is
`FFFixedEarlyGroup`, `OrderFirst` — the fingerprint samples a full transform pass AFTER the KD-tree
has already consumed its input (`KnnSystem.cs:332-353`, `TryGetBuildWitness`'s own docstring names
this "THE BLIND WINDOW THIS CLOSES"). Two BEAST reproductions forked with every end-of-heartbeat
aggregate reading clean — `tier4Src=0`, `pendingSrc=0`, equal poses, equal `enemySrcSeq` — while the
actual KD-tree build input differed between peers on the heartbeat a spawn wave entered the
population (no earlier row existed yet to compare against, either). **Fix: digest the ACTUAL
retained buffers at the consumer**, not an `EntityManager` re-query at report time —
`KnnSystem.TryGetBuildWitness` hands back the post-sort `Sources` prefix and the new
`KnnVisionWitness` `Build*`/`View*` fields (`DeterminismStateFingerprint.cs:6210-6256`,
`FoldKnnBuildSources`). A digest whose sub-hash folds only fields that CAN'T differ is structurally
blind to the fork it exists to catch: the OLD `…SrcSeq` sub-hash folded only `(id, keyed, pose)`
(`DeterminismStateFingerprint.cs:6217-6224`) — two entries whose key AND pose are equal (the exact
residue an unstable sort leaves behind) folded IDENTICALLY on both peers, which is why 1611 forking
heartbeats reported `enemySrcSeq` agreement.

## Rank hypotheses, then build the instrument that discriminates them, BEFORE designing a fix (R36→R37)

R37's commit message (`f9c91d268`) states it directly: "R36's instrument discriminated the
hypotheses and refuted every one of them: BuildDupKey=0/BuildTier4=0/BuildUnkeyed=0 on every
heartbeat (no canonical-key tie), BuildN equal (no membership split)... What is left is the one
thing the roster cannot see." The new `BuildDupKey`/`BuildTier4`/`BuildUnkeyed` fields refuted the
ranked-first hypothesis — a stale sort producing a canonical-key collision — in one sweep;
`BuildN`/`BuildSeq`/`BuildSet` equal-vs-differing then localized the fork to a transient-input class
in the pre-build/post-fingerprint window, which R37 traced to an absent `LocalToWorld` writer (see
[[fixed-group-reads-of-localtoworld-are-frame-count-bugs]] for that fix). **Rule**: rank your
hypotheses, then build the instrument fields that would discriminate between them, BEFORE picking a
fix — the fix the naive first hypothesis (stable sort) implied here would have been wrong.
