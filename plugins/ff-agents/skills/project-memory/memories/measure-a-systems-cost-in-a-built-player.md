---
name: measure-a-systems-cost-in-a-built-player
description: "A system's cost per heartbeat on a big save, in a built development player: a ProfilerRecorder on every marker whose name holds the system's name (its jobs included, worker threads counted) over a window of heartbeats, with the per-frame p50/p95/p99, so a cost every 4th heartbeat shows as a spike instead of a mean; a measurement ffauto verb writes the load. Editor numbers with job safety checks differ several-fold."
---

# Measuring a system's cost in a built player (2026-10-12, w1046 circuits)

Ben: "make sure this is performant, adds no real performance cost to the simulation". What worked:

- **Instrument**: an ffauto dev verb pair (`circuit.perf|start` / `|read`, FinalFactory `CircuitPerfCommands.cs`):
  `ProfilerRecorderHandle.GetAvailable` -> every handle whose name contains the system's name (ECS gives the system
  a marker `Default World FFSystems...System`, and each job `System:Job (Burst)`), `new ProfilerRecorder(handle,
  16384, SumAllSamplesInFrame | StartImmediately)`, then sum the samples over the window and divide by the heartbeats
  that passed (`Heartbeat.CurrentHeartbeatFrame`). A MonoBehaviour gets its own `ProfilerMarker` to be found.
- **Spread**: also sum the markers per frame and print p50/p95/p99/max. A system that works every Nth heartbeat has
  p50 near 0 and the cost in the tail; after spreading the work over the N heartbeats p50 equals the mean.
- **Load**: a measurement verb that writes the components directly on a real big save (`circuit.bench|<n>`,
  `w225-bench-JustPlay`, 137,585 structures), the worst case (nothing settles early), in a Deck tour's `setup` steps
  (`make_perf_tour.py` in `specs/092-circuits/tour/`). The job times are summed over worker threads: an upper bound.
- **Editor vs player**: the editor's job safety checks inflate a per-heartbeat fixed cost several-fold (the synthetic
  benchmark read 0.108 ms where the player read the job work alone); take the verdict from the player.
