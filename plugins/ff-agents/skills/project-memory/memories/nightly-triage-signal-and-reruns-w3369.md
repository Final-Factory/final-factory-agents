---
name: Nightly triage: shrunken raids, quiet reruns
description: w3369 (2026-11-07). A balance scenario whose raids shrink: set FreeStability high in the editor to find the cause; quiet reruns need a fresh player and a released bench ticket
type: project
---

Learned while triaging w3369, the 12 nightly e2e failures of 2026-11-07 on master 5ccfabf239.

**A balance scenario whose raids shrank (attackers, waves, the frontier flags).** Raid size comes from the global
signal. A station grid emits nothing while it is unstable: `CalculateTotalSignalStrength` returns 0 when
`!IsStable(FreeStability)`, and `IsStable` compares Core + NonCore + FreeStability against `NeededStability`, which already
has the strut reduction taken off (`StationGridCalculationSystem.cs`, `grid.NeededStability -= grid.StrutReduction`).
Signal is not saved: every emitter reads 0 at load, so diffing two saves tells you nothing. Instead:
1. Load the scenario's save in the editor and let it run 90 s.
2. Read the total `StationGrid.SignalEmitted`, and count the grids with `!g.IsStable(70)`.
3. Set the `GlobalConfig` singleton's `Stations.FreeStability` to 100000, run 90 s more and read the total again.
4. If the forced-stable total matches the old baseline, unstable grids are the whole cause. Then count each unstable
   grid's items by `Placeable.UintId` (`ItemConfig.GetIdForName` takes the asset's display `_name`, e.g. "Strut" or
   "Singularity Power Station", not its file name) to tie it to a rule change.

Measured on the w1440 meltcpu save: 17,094 at FreeStability 70 (85 of 1,674 grids unstable) against 57,979 forced
stable, with a baseline of 57,293. All 85 unstable grids carried struts; making struts and Singularities free again
made 56 of them stable. The cause was PR #3234 (w3193) and PR #3278 (w3260/w3261). Ben's answer on 2026-11-07: "Do
nothing right now. We are figuring out what to do with struts". Put FreeStability back to 70 afterwards.

**Quiet reruns.**
- `bench_queue.py timed --release` run from inside a script did not free the background `timed` holder, and the next
  leg waited on it. End the holder process itself, or `ff-leftovers end`.
- A player you built earlier in a long request may be gone by your late reruns: the daemon sweeps idle builds. Rebuild,
  or check the exe exists, before you call a rerun's failure real.
- A scenario's own nightly history may hold only the failing night (SP-W1380 had no earlier run in
  `nightly-history/runs`). Look for another scenario on the same save that logs the same line, for example the
  `[EnemyPressure] chunk=... stations=N` line.
