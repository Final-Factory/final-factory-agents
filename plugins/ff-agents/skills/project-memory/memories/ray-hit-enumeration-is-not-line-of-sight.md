---
name: ray-hit-enumeration-is-not-line-of-sight
description: "074 T121: identical physics hit multisets arrived in different orders on three physical peers, so first-target/first-blocker returns forked retained combat targets. Trace the actual consumed hits, then use a distance reduction with explicit ties and unchanged ignore precedence."
---

# Ray-hit enumeration is not line of sight

`CollisionHelper.PerformRaycastAll` returns Unity's all-hit collection. `AllHitsCollector.AddHit`
appends hits; its order is not a nearest-first contract. Never let the first target or blocker in
that collection decide a gameplay branch. Source: `TargetingSystem.TargeterJob.IsInLineOfSight`
and `HasLineOfSight`; `CollisionHelper.PerformRaycastAll`; Unity Physics `AllHitsCollector.AddHit`.

Feature074 t30 at92437838c captured the actual consumed rays on M5, M3 and BEAST. All12 affected
ships had matching source/target poses, target health/eligibility and raw/resolved hit multisets.
For actor687, target tile(-90,0,-13) had fraction bits1064155070 (0.9285849333); blocker
(-90,0,-12) had1063128464 (0.8673944473). Host enumerated target first and accepted LOS;
both clients enumerated the nearer blocker first and rejected it. Parent compared multisets
while excluding peer-local Entity handles and hit ordinal. Evidence:
`/private/tmp/ff073-hazel-20260915/xplat/t30-artifacts/verified-los-root-cause.json`.

Repair3fb929bd6 reduces nearest target and nearest nonignored blocker independently. A blocker
at equal distance wins; absent a target hit, the ray endpoint remains the target distance.
Preserve collider-parent resolution and self/player/weapon-owner/ignore precedence. Do not sort
by Entity.Index or dismiss inactive-looking structures as blockers without tracing the policy.
`CombatTargetingTest` permutes near/far/tied hits and the exact live fractions: RED5/12 expected
failures, GREEN12/12. T31's first8-heartbeat targeting outputs match across all3, but that leg
failed later on separate construction timing (T122); it is not a clean full-leg acceptance.

A target-loss symptom may show one heartbeat later in movement/laser markers. Trace actual
inputs at the consumer before changing those downstream transitions. Aggregate combat/mover
hashes are not proof that ordinary station targets or health agree: inspect exactly which fields
the fingerprint folds (`DeterminismStateFingerprintJobs.ComputeCombatHash` and mover providers).
