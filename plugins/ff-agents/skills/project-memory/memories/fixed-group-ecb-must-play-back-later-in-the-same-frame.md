---
name: fixed-group-ecb-must-play-back-later-in-the-same-frame
description: "A fixed-group system that defers a structural change through an ECB whose buffer system already played back THIS engine frame (FFEarlyBufferSystem, OrderFirst in Simulation) lands it at the start of the NEXT ENGINE FRAME, and whether that frame carries a heartbeat is per peer. Every FixedEarly reader then sees the entity one heartbeat apart per peer — the R27 class (controller-cadence write feeding a fixed-group read) wearing an ECB. 073 T033: SwapStation's replacement structure through the Early buffer; six one-heartbeat census blips in leg g12d, the hologram colour initializer marker on the client only. Fix 1174e30bd: record into FFLateBufferSystem (end of the SAME frame, after PlaceableDeletionSystem, before DeletionSystem). Defer within the frame, never across it."
---

# A fixed-group ECB must play back later in the SAME engine frame (073 T033, 2026-09-18)

**The shape.** `ConstructionBotTaskSystem.SwapStation` (`FFFixedPreTransformGroup`) wanted the replacement structure
created "after all the deletion/cleanup" of the structure it replaces, so it recorded the copy into
`FFEarlyBufferSystem`'s ECB. That buffer system is `OrderFirst` in `SimulationSystemGroup`
(`SystemGroups.cs:116-159`) and had ALREADY played back this frame, so the copy was created at the start of the
NEXT ENGINE FRAME. Whether that frame is heartbeat N+1's frame is per peer (frame rate, lockstep catch-up): on the
peer whose next frame carried the heartbeat, `FFFixedEarlyGroup` ran before the Early playback and saw the copy one
heartbeat later than the other peer. Readers in that group: `KnnSystem`, `C3StaticIndexMaintenanceSystem`,
`DefensePlatformDefenseSystem`, `HealthBarCreatorSystem`, `HologramMeshBaseColorMaterialPropertyInitializerSystem`
(`grep -rn "UpdateInGroup(typeof(FFFixedEarlyGroup)"`). Later fixed groups were unaffected: the Early playback
precedes them either way, which is why grids and power stayed green while `census` blinked.

**The tell.** Isolated single-heartbeat `census` mismatches, equal again the next heartbeat, each one a JUST-CREATED
entity (here: `InstantiationUpdaterMarker` + `NeedsConnectionsUpdate`) still carrying a FixedEarly system's
initializer marker on one peer only, plus the old entity's hologram child lingering one heartbeat longer on the
other (leg g12d: hb 695, 873, 881, 893, 898, 899 — same three rows every time). Same family as
[[fixed-group-engine-time-reads-are-frame-rate-desyncs]] and R27 in
[[join-load-route-provisioning-desync-class]]: a value that depends on how many ENGINE frames elapsed, read at
heartbeat cadence.

**The fix shape.** Record into a buffer system that plays back LATER IN THE SAME FRAME: `FFLateBufferSystem` runs at
the end of the frame after `PlaceableDeletionSystem` (`FFControllerLateGroup`) freed the tile and before
`DeletionSystem` destroys the old entity (`DeletionSystem.cs:14` `UpdateAfter(FFLateBufferSystem)`) — exactly the
ordering the original comment wanted — so every fixed system on every peer first sees the copy at heartbeat N+1.
Guard: `SwapStationInstantiationCadenceTest` (exists after the same frame's Late playback, NOT created by the next
frame's Early playback). Rule: from a fixed group, defer WITHIN the frame (Late buffer / the group's own ECB), never
ACROSS it (Early buffer). Which recorders cross the frame: `FFFixedEarlyGroup` is `OrderFirst` and
`FFEarlyBufferSystem` `OrderLast` in the SAME `FFControllerEarlyGroup` (`SystemGroups.cs:116-159`), so a FixedEarly
system recording into the Early buffer plays back later in the same frame (fine); a recorder in any group AFTER that
playback (PreTransform onward) lands next frame. Census 2026-09-18 (`grep -rn "FFEarlyBufferSystem.Singleton"
Assets/Scripts/FFSystems`, 8 recorders): six are FixedEarly (`HealthBarCreatorSystem`, `CometCatcherSystem`,
`HologramMeshBaseColorMaterialPropertyInitializerSystem`, `ScalableLaserSystem`, `InserterMovementSystem` ×2), one
controller-cadence (`PresentationRotatorTaggingSystem`), and ONE remaining cross-frame candidate:
`HealthBarSystem.cs:14` (`FFFixedPreTransformGroup`) — not chased; trace whether what it records is simulation-visible
before touching it.

**Proof.** Unit RED (job `7329f2ee…`) → GREEN (`6f25c60a…`); fast suite `9893df30…` 4275 / 0 failed / 16 ignores;
built pair `1174e30bd` (Mac host, BEAST client, hazel1831, r8 chain) leg g13: 5,189 shared heartbeats, typed `mismatchCount` 0, 0 verdicts, 0 recoveries, `census` equal on EVERY shared heartbeat (g12 on the previous sha had 4 `census` heartbeats; the only remaining differing field is the by-design-exempt `playerInventories`, see [[player-inventory-arrangement-diverges-by-design]]).
