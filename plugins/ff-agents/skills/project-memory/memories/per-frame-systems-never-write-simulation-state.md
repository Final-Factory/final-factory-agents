---
name: per-frame-systems-never-write-simulation-state
description: "Direct members of the FFController* groups, PresentationSystemGroup members and ungrouped systems run every rendered frame, a peer-dependent number of times per heartbeat; they must write nothing the simulation reads. Move a writer OrderLast into its own controller group's fixed subgroup. PerFrameSystemCensusTest guards the class."
---

# Per-frame systems never write simulation state

**The class.** Each `FFController*Group` holds an OrderFirst `FFFixed*Group` (runs only when a new
heartbeat was applied) and an OrderLast command-buffer system (plays back every frame). A system
placed directly in the controller group, in `PresentationSystemGroup`, or nowhere (default
`SimulationSystemGroup`) runs every rendered frame. `HeartbeatSystem.PerformQueuedOperations`
applies the ops ahead of heartbeat N, then N, then stops, so a ~20 fps host applies an op and the
next heartbeat in one frame while a 60 fps client runs every per-frame system in between. Anything
such a system writes that a fixed system, an op or the fingerprint reads forks the peers by frame
rate (w342: the per-frame deletion chain and item recount; a Steam Deck host forked alone).

**What w356 found and moved (2026-10-04, #1025):** `HeatReceiverSystem` (saved `HeatProducer`,
read by the grid calculation), `DisabledKnnWanderSystem` (saved `LinearMotion.Disable`; its query
also lacked `LinearMotion`, so the EDITOR threw and skipped it while release players ran it),
`NetworkedInventoryCacheUpdaterSystem`, `StarPlacementSystem`, and `FFDisableMovementMarkerSystem`'s
attach of `FFLtWToggle` to every transform entity (an archetype change the census counted; now
`FFLtWToggleAttachSystem`, fixed). Also #1028: the host's hauler request leg advanced the saved
stop counter alone. #1029: the census counted 77k presentation entities through `FFLtWToggle`
and took 54 ms instead of 7 ms per sample on a 130k-entity save. Audit:
`specs/w356-sim-presentation-audit/AUDIT.md` in the game repo.

**How to apply.**

- Placing a system: simulation goes in a fixed group. Per-frame is for presentation only.
- Moving a per-frame writer: OrderLast in its own controller group's fixed subgroup, after the
  subgroup's existing OrderLast system (`UnitOverlapPreventionSystem` in PreTransform,
  `DeterminismPostApplyFingerprintSystem` in Late), so a heartbeat frame runs it exactly where it
  ran before. Keep its command buffer: the controller's buffer still plays back after the fixed
  subgroup in the same frame.
- Pin it with `PerFrameSimulationWriteTest`'s pattern: build the controller group, its fixed
  subgroup and its buffer system, place the system by its own `UpdateInGroup`, run a frame without a
  heartbeat (nothing may change), then one with (the change lands).
- `PerFrameSystemCensusTest` lists every per-frame system with its reason; it fails on a new one,
  a stale entry, or a `[Save]` write its entry does not list.
- A custom query passed to an `IJobEntity` must contain every component its `Execute` takes; the
  editor throws without it and release players run the job anyway, so a missing term is an
  editor-only skip.
