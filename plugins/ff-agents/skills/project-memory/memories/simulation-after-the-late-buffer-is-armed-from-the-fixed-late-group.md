---
name: simulation-after-the-late-buffer-is-armed-from-the-fixed-late-group
description: "Something that must follow a mobile station (or anything else moved from FFLateBufferSystem) cannot be placed in a fixed group: no fixed group runs after that buffer. Predicting the mover's step slips a heartbeat whenever another mover acts. Put the follower after FFLateBufferSystem and arm it from a system inside FFFixedLateGroup (StationShipCarrySystem, w165 #936). The interpolation capture runs before the late buffer, so whatever the follower moves must have its captured pose moved too."
metadata:
  type: project
---

# Simulation that follows a late-buffer write: after the buffer, armed from the fixed late group (w165, #936, 2026-10-02)

**The case.** A Defense Platform's parked Bats sat 17 to 28 u behind their slots on a flying station. Two fixes that
predicted the platform's velocity were built and measured before the one that merged.

**Who moves a station, and when** (all through `cb.SetComponent` on each grid item, `MobileStationUtils.cs:156`,
`:212`, `:502`; none writes `LocalTransform` directly):

| Mover | Group | Buffer |
|---|---|---|
| Transit (`MobileStationTransitSystem.cs:190`) | fixed pre-transform | `FFPreTransformBufferSystem` |
| Landing approach and descent (`MobileStationDockingSystem.cs:231`, `:407`) | fixed pre-transform | pre-transform and late |
| Lift-off (`MobileStationUndockingSystem.cs:374`) | fixed late | `FFLateBufferSystem` |
| Hand driving (`HaulerManualDriveApplySystem.cs:151`) | fixed late | `FFLateBufferSystem` |
| Black hole pull (`BlackHoleDeathSystem.cs:197`) | fixed post-transform | `FFPostTransformBufferSystem` |

Fleet ships are moved in the fixed pre-transform group (`FleetIdleStationSystem`), before any of these lands.

**What does not work.**

- A velocity fed to the ship's own steering: the ship still accelerates and brakes (5 u behind after a start, 8.7 u
  past its slot at a stop).
- A step predicted from the hand drive's replicated intent, with the last heartbeat's step for automation: exact for
  hand driving, one step late for everything else. Built runs showed 8.2 u at a platform far from the pivot when a
  landing station starts its alignment turn and 4.6 u at lift-off (a zero-length transit with a temporary stop sits
  between the lift-off rail and the hand drive). A station taken over by hand on its route also keeps
  `InTransitState` (`HaulerCommandOperations.PrepareForDriving` only switches the automation off), so "which mover
  acts this heartbeat" is not readable from the state alone (`MobileStationUtils.CheckICanMove`: automation on, or a
  temporary stop).

**What works.** Observe the step instead of predicting it: a system placed after the late buffer,

```csharp
[UpdateInGroup(typeof(FFControllerLateGroup), OrderLast = true)]
[UpdateAfter(typeof(FFLateBufferSystem))]
```

that does nothing unless a tiny system inside `FFFixedLateGroup` armed it this frame
(`StationShipCarrySystem` / `StationShipCarryArmSystem`, `Assets/Scripts/FFSystems/Fleet/StationShipCarrySystem.cs`).
`DeletionSystem` sits in the same place.

**How to apply.**

- Arm it from the fixed late group and from nothing else. A gate on the heartbeat number or on "something moved" also
  fires in a frame without a heartbeat, and which frame that is differs between peers (an operation applied between
  two heartbeats lands in its own frame on one peer and in the next heartbeat's frame on another). A group's own rate
  manager also decides pause cases (`FinalFactorySimulationRateManager.ShouldGroupUpdate`), so do not copy its test.
- Take the step from simulation state both peers hold: `LocalTransform` now against a position saved at this
  heartbeat's fixed pre-transform group (`FleetCommander.LastFleetPosition`, written by `FleetCommanderSystem`). Move
  the reference up after use, so a second run moves nothing twice.
- Use `HeartbeatData.SimulationFixedFrameTimeInSeconds` for time. Outside a fixed group `FFTimeData.deltaTime` is the
  engine frame's (`FinalFactoryFixedStepSystemGroup.SetDeltaTimeAndCallUpdateOnGroup` restores it).
- **Move the captured pose too.** `WorldEntityInterpolationCaptureSystem` runs in `FFFixedPostTransformGroup`, before
  the late buffer. An entity the follower moves afterwards is drawn from the pose captured before the move: one step
  behind for as long as the station flies. Add the step to `WorldEntityPresentationInterpolation.CurrPosition` when
  `CapturedHeartbeatFrame` is this heartbeat's (presentation only, not saved).
- The paired audit sees a fleet ship's position through the `movers` fingerprint: its combat rail is rewritten from
  `LocalTransform` every heartbeat (`CombatMoverRailMirrorSystem`). The `fleets` fingerprint holds counts only.
- Before predicting anything that follows a moving thing, list every writer of its position and the buffer each one
  plays back from. If one of them is the late buffer, prediction will be late for the others.
- Pattern note in the game repo: `docs/dots-reference.md`, "Simulation that has to see what the late buffer wrote
  this heartbeat". Write-up: `specs/mp-station-riders/bat-slot-feed-forward.md`.
