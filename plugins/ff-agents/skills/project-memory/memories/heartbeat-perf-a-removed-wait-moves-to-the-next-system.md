---
name: heartbeat-perf-a-removed-wait-moves-to-the-next-system
description: On big saves the fixed-group heartbeat is bound by serial job chains, and a system's main-thread time is mostly JobHandle.Complete; removing one such sync point moves the wait to the next system that completes the same jobs, so judge a perf change on the whole heartbeat, not on the system
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

**How to apply:** before claiming a perf win, measure the whole heartbeat A/B in built players with
`-ffBenchSystems 1` and `scripts/bench/ab_summary.py` (median of the top-level fixed groups, interleaved runs,
several rounds), not the changed system's own time. In a profiler capture, split a system's time into its
`JobHandle.Complete` part and its self time first: a wait is only worth removing together with every later
wait on the same chain. Contention from other sandboxes still applies:
[[beast-shared-machine-perf-ab-side-by-side]].
