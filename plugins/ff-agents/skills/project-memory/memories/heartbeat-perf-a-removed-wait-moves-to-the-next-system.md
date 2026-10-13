---
name: heartbeat-perf-a-removed-wait-moves-to-the-next-system
description: On big saves the fixed-group heartbeat is bound by serial job chains, and a system's main-thread time is mostly JobHandle.Complete; removing one such sync point moves the wait to the next system that completes the same jobs, so judge a perf change on the whole heartbeat frame (PlayerLoop on heartbeat frames, not only the fixed groups: w1200's wait moved into per-frame MouseRaycastSystem), not on the system
metadata:
  type: project
---

On the big saves (Strange, bigAmazingSaveForTrailer, JustPlay; w225, 2026-10-03, built bench players on
BEAST) about 16 of the 25 ms of fixed-group main-thread time per heartbeat is spent in `JobHandle.Complete`, and
31 worker threads sit mostly idle: the heartbeat is bound by chains of jobs that run one after another (knn,
the crafter and station-grid chain, the physics build, `SignalCalculationSystem` every 8th heartbeat). Whichever
system first reads their output on the main thread pays the wait: `EntityManager.GetComponentData<T>` and
`SystemAPI.GetBuffer<T>` complete every writer of `T`, `Ecs.CollisionWorld` completes the physics build,
`CompleteDependency()` completes everything the system declared.

Moving such a read into the job is correct and drops that system to ~0 ms, and the heartbeat does not move:
the next system pays the same wait. Measured: `CometSpawnerSystem` 4.8 → 0.03 ms, and
`AncientPortalCollisionSystem` (its `CompleteDependency()`) 0.014 → 4.86 ms; `DeathSystem` 4.3 → 0.01 ms with
no heartbeat change on three saves (`Documentation/Performance-Simulation-Big-Saves-2026-10-03.md`). What did
shorten the heartbeat was removing pure main-thread WORK (`HaulerManualDriveApplySystem`, #954: −1.8 to −4.4 ms).

**The wait can leave the fixed groups altogether** (w1200, 2026-10-13, LifeSave, built bench players, base against
branch alternated twice): replacing `AncientPortalCollisionSystem`'s physics raycast took the system from 0.97 to
0.016 ms and the fixed-group total from 6.78/6.39 to 5.78/5.49 ms, a "win" by the old rule below. But
`MouseRaycastSystem` (`FFControllerEarlyGroup`, every frame, reads the CollisionWorld) rose from 0.10 to 1.03 ms on
the same heartbeat frames, `SimulationSystemGroup` stayed at 11.2 ms and the frame did not shorten. The brief had
assumed the 0.97 ms was the ray; one world ray costs about 20 us, the rest was the physics-build wait.

**How to apply:** before claiming a perf win, measure the whole heartbeat FRAME A/B in built players with
`-ffBenchSystems 1`, interleaved runs, several rounds: `python scripts/bench/analyze_systems.py <before>/save-idle
<after>/save-idle` prints `PlayerLoop`, `SimulationSystemGroup` and `PresentationSystemGroup` on heartbeat frames and
the largest drops and rises (game repo #1629); a drop matched by a rise moved. The top-level fixed groups alone
(`ab_summary.py`, the "heartbeat total") miss a wait that moves into a per-frame system. Never judge by the
changed system's own time. Before proposing to remove a wait, name the next main-thread reader of the same jobs
(for the physics build: `Ecs.CollisionWorld` / `GetSingleton<PhysicsWorldSingleton>` callers, per frame included). In a profiler capture, split a system's time into its
`JobHandle.Complete` part and its self time first: a wait is only worth removing together with every later
wait on the same chain. Contention from other sandboxes still applies:
[[beast-shared-machine-perf-ab-side-by-side]].

**w1203 (2026-10-13, LifeSave, lothdesktop): the per-frame case.** Four job-only `Ecs.CollisionWorld` callers moved to
`SystemAPI.GetSingleton<PhysicsWorldSingleton>()` (the job chains after the build, nothing syncs in a player).
FindNearbyHaulers fell from 0.7-1.3 to 0.01-0.05 ms a heartbeat, MouseRaycast from about 1 ms a frame to 0.04-0.10,
and frame and heartbeat stayed the same in eight 180 s runs: `FFEarlyBufferSystem` took the wait, because an
`EntityCommandBufferSystem` completes its producer jobs and the raycast job now chained after the physics build.
Two traps on the way: MouseRaycast's wait was not the getter at all but `PlayerDataController.SimulationPosition`, a
main-thread `LocalTransform` read, which completes Unity Physics' `ExportPhysicsWorld` (a registered `LocalTransform`
writer) and so the whole physics pipeline; and its `JobHandle.Complete` sits directly under the system's marker, so
only a wait-path digest (`rawreader/WaitPaths.cs`) plus reading the update's main-thread calls finds which call it is.
Game repo `Documentation/Performance-CollisionWorld-Sync-2026-10-13.md`.
