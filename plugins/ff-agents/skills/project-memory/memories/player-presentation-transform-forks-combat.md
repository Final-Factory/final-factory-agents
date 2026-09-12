---
name: player-presentation-transform-forks-combat
description: "Any simulation decision that reads a PLAYER's LocalTransform/LocalToWorld forks per peer — that transform is the local player's own motion on one peer and a RemoteLocalTransformTarget projection on every other. OldBeamShootingSystem's beam range gate did this: BeamDamageSystem ticked 0.165 hp/s into the player on the host only → `combat` fork, re-fork at hb 8 after every recovery, Steam kick. Fixed 4aabc5d4a via DeterministicEntityPosition. The projectile-on-remote-player KNN path is NOT in this class: the player's KNN presence is its PlayerSimulationObject, anchored at Player.SimulationPosition every heartbeat."
---

# A player's transform is presentation; every range/hit/aggro decision about a player must resolve via DeterministicEntityPosition (2026-09-12, 069)

**Symptom.** Ben's Steam client was kicked from Loth's host after every recovery load: `[DesyncDetector]`
lines on `combat` (and downstream `camps`/`attacks`) at 8-heartbeat sample boundaries. Reproduced on
our own identical-build pairs only when the HOST's OWN player was under fire near a camp — a Windows
host + Mac client (r8, r9b) and a Mac host + Mac client (r9c) all forked; an idle or freshly-loaded host
never did, and a host whose player took no damage never did. Not platform codegen.

**Mechanism (path-traced).** `combat` folds per-player IsDefeated / Health.CurrentHealth / invuln
expiry / riding (`DeterminismStateFingerprintJobs.cs:800-860`). The diagnostic `PlayerCombatDetail`
dump showed the host subtracting exactly 44,291,851 raw (0.0103125 hp = 0.165 hp/s at 16 UPS) from
its player every heartbeat while the client's copy stayed at full health. Constant per-heartbeat
damage = a beam (`BeamDamageSystem.cs:86-96`, damage × Dt while `ScalableLaserOwner.IsOn`). The
legacy enemy beam's on/off + range gate, `OldBeamShootingSystem.cs:70`, read
`AllLocalTransforms[targetEntity].Position` — for a player that is PRESENTATION: the local player's
own motion on one peer, a `RemoteLocalTransformTarget` projection on every other
(`PlayerAuthoring.cs:110-119`). The gate flipped per peer, so the beam was on for the host only.

**Fix `4aabc5d4a`.** `DeterministicEntityPosition.ResolveLocalTransform(targetEntity, Players,
AllLocalTransforms)` (→ `Player.SimulationPositionFloat3()`), exactly what `OldShootingSystem.cs:105-107`
and `NewBeamShootingSystem.cs:66-73` already did ("blue-planet engagement desync"). Test
`OldBeamShootingPlayerPresentationTest` mirrors `OldShootingPlayerPresentationTest`. GREEN: the same
fights on both topologies, 0 mismatches across 2203+3221 and 1464+2619 compared samples incl. forced
reloads and a host player driven to hp 21 under beam fire.

**Rule / how to apply.** Grep any new or legacy combat decision (range, hit, LOS, aggro, aim) for
`LocalTransforms[...target...]`, `LocalToWorldLookup[...target...]`, or KNN entries built from poses,
and ask "can the target be a Player?" If yes, resolve through `DeterministicEntityPosition` (or
`DeterministicRailPosition.Classify` as `ChaseSystem.cs:472-482` does).

**Retracted 2026-09-12 (relay #5):** the earlier claim that projectile hits on a REMOTE player were the same
open class was wrong. The player entity carries no KNN component (`PlayerAuthoring.cs:193-200`,
`KnnChunkPoses.cs:64-69`); its KNN participation is the invisible `PlayerSimulationObject` authored with
`KnnFleetEntity` + `KnnEnemyVision` and the redirects `ColliderParent` / `PhysicsRenderEntity { Entity = player }`
(`PlayerSimulationObject.cs:79-93`), and `PlayerSimulationObjectPositionSystem.cs:52-53` writes that object's
`LocalTransform.Position` from `Player.SimulationPosition` every heartbeat. So the KNN vision entries
`KnnProjectileCollisionSystem.cs:137-158` ranks are the sim object at the replicated position, the hit redirects
to the player at `:165-168`, and the physics path skips players outright (`ProjectilePhysicsCollisionSystem.cs:87-90`).
Before opening a "presentation transform" lane on a KNN consumer, check whether the player is even in the tree
as itself. Related: [[steam-desync-triage-from-the-client-side-only]], [[diagnostic-profile-config-recipe]].
