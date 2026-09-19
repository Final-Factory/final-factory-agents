---
name: request-apply-conversion-must-keep-the-release-owner-too
description: When converting a local cast into a request/apply op pair, the op-carried RELEASE edge must match the kind's ORIGINAL release owner, not just its gate owner — the Obliterator's config Duration is the disc's flight lifetime, so a Target+Duration release would have freed its Krillos before the charge and deleted the disc (073 T030); plus the every-peer spawn recipe (deferred ECB entity as a component reference)
metadata:
  type: project
---

# A request/apply conversion must keep the release owner, not only the gate owner (073 T030)

[[silent-host-rejects-look-like-a-dead-ability]] says: keep the ORIGINAL gate owner (per-ship vs
per-player). T030 added the second half: keep the original RELEASE owner too. The generic
mover-command applier (`CombatAbilityCommandApplySystem`) stamps every commanded ship with
`DeterministicAbilityRelease = Target + config.Duration`. That is right for Guardian/Frenzy, whose
Duration IS the hold. For the Obliterator disc, `Duration` (1.3 s) is the disc's FLIGHT lifetime
(`ObliteratorDiscJob` → `LimitedLifetime`); the Krillos legacy-released when the disc LAUNCHED
(`MultiUnitCastAbilityTracker.Finished`, `GoToSpotAbilityJob`'s second branch), after a 2 s charge
plus travel. Stamping the op release would have freed them at 1.3 s and `ObliteratorDiscJob` would
have deleted the never-launched disc: converted, deterministic, and dead.

**How to apply:** for each kind you convert, read what ENDS the effect today and cite it; if it is
not `Duration`, the applier must not add the op release for that kind (and say why at the site).
The remaining float edge (the disc's `ScaleOverTime` charge) is a named residual (073 T034), not
silently laundered into "deterministic".

**The every-peer spawn recipe that worked** (`SpawnObliteratorDisc`): resolve the prefab by NAME
on the native side (`ItemConfig.IdToNameLookup` scan — `GetIdForName` has managed string compares),
`commandBuffer.Instantiate(prefab)` → the DEFERRED entity is legal inside component data set
through the same ECB (`CastArgs.EffectReference = disc` on the disc AND on its ships; the
`GoToSpotAbilityJob` effect precedent) and as the target of `AddBuffer<MultiCastShip>`; read the
prefab's own `Projectile` with `EntityManager.GetComponentData(prefab)` to patch damage; resolve the
crew FIRST and spawn nothing on an empty crew (a crewless disc never charges and never dies).
Unit-proven with `EcsTestBase`'s seeded `ItemConfig` (fill one `ItemPrefabs` slot + one
`IdToNameLookup` row; the NativeArray/HashMap are views, so a struct copy writes through).
