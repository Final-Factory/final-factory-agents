---
name: warm-vs-load-order-and-stale-derived-state
description: "The desync class behind the 0.50.0.22 live 'camps at hb 8 after every serve' cascade: simulation that reads a buffer's ORDER (build history) or an unsaved derived value off its own cadence gives a freshly served peer a different answer than the warm host. Load-vs-load probes and harness legs that start from a save can never see it. The probe that does, and the two fixes (074, 2026-09-23)."
---

# Warm vs load: history-dependent order and stale derived state (074, 2026-09-23)

**The shape.** A join or recovery serve reloads ONE peer from the host's snapshot while the host and
the bystanders keep their live worlds. Anything the simulation reads that is (a) the ORDER of a
buffer built up by history, or (b) a derived, unsaved value read before it is recomputed in the new
epoch, differs between the reloaded peer and the warm ones. Signature in the live reports: the HOST
is the odd one out (both clients share one fingerprint), the host's surface hash is unchanged across
the serve, and the fork shows at the first sample (hb 8) after every serve.

**Two instances, both fixed:**
- `SignalCalculationSystem` credited a grid's whole signal to the chunk of `gridItems[0]`.
  `StationGridItem` order is history: a warm world appends members and regrids from its old order,
  while a load rebuilds each grid in load order. Camps absorb from, and attacks target from, per-chunk
  maps that no surface hashes. The grids hash sorts member tiles, so only the camp ledgers showed it.
  Fix `20125d1ee`: the canonical member is the one with the smallest grid tile.
- `EnemyCampBuilderSystem` read `GlobalSignal` every heartbeat. It is rewritten only on the final calc
  step and never saved, so for heartbeats 0-6 after a reset each peer held a different leftover.
  Fix `ecd3cbd85`: `GlobalSignalData.IsCurrent` is cleared by `HeartbeatSystem.ResetHeartbeat` on every
  peer and set on the final step, and the builder waits for it.

**Why the usual probes missed it.** Saving and then reloading compares two LOADS, which agree. Every
harness leg that starts from a save file starts the host from a load too. The live trigger was
in-session history: players deconstructing or building stations.

**The probe that finds it (editor, ~10 min).**
1. Load the save.
2. Apply the in-session mutation, e.g. `DeletionMarker` on the first member of each multi-chunk
   grid, or on anything whose container order matters.
3. Step, then dump the DERIVED value the consumer uses (here: each grid's attribution chunk, and
   `GlobalSignalData.ChunkResults`).
4. Background-save, reload (confirm the heartbeat went back to 0), step, dump again, diff.

Measured: 5 of 88 grids moved chunk (warm (5,4) vs reloaded (4,4), beside a camp at (6,4)).

**MP proof recipe.** Host `construction.remove` of those first members, walk the host within bot
range, wait for the regrids (`RegridTrace` removes), then `desync.forceresync|1`. Diff
AttackScheduleDetail (legacy capture, hb <= 8 per epoch) for host vs served client vs bystander.
- RED: the served client had 9 chunk results vs 8, with differing values; the bystander matched the host.
- GREEN: all three identical at 109 keys.

**When auditing a new consumer:** grep for `[0]` on a DynamicBuffer, for "first processed wins"
maps, and for singletons holding NativeReferences that are written on a cadence but read every
heartbeat.
