---
name: hidden-ship-stale-knn-vision-forks-host-vs-joiner
description: "w197, live 0.50.0.64: Bats in Chase on the host only (fixed by PR #924). A ship out of the KNN (DisableKnnMarker) keeps the vision of its last refresh on a long-running peer and has none on a peer that loaded; the un-hide heartbeat targets from it. Not CPU architecture: the Steam Mac build runs x86_64 under Rosetta and Burst float there equals Windows."
---

# A hidden ship's stale KNN vision forks host against joiner (w197, 2026-10-02)

Report `20261002T043752Z-desync-f4f4952e62`: 3,544 heartbeats after a join, 6 of the host's 44 Bats
were in Chase on the host and idle on the client (`movers+census`). FFBox blamed Apple Silicon
against x86 float. It was a join-state gap. Desync board rounds 7 and 8 hold the detail.

**Fixed by PR #924 (w214):** `KnnSystem` empties the vision of every holder with `DisableKnnMarker` (parked
`Disabled` ones too) each refresh, and so does the C3 path's `LegacyVisionShimSystem`. Nothing new is saved. Two
things surprised:

- A test had pinned the bug. `KnnLegacyVisionCharacterizationTest.IneligibleHolder_KeepsItsStaleBufferFrozen`
  (and a shim test) asserted the frozen buffer on purpose, as the legacy contract to preserve. Before calling
  a stale buffer "the contract", ask whether a peer that loaded would hold the same one.
- The detector misses it when no ship is free to take a target. On the pre-fix build, Mac + Mac runs of
  `W197-stale-vision-unhide` passed 3 of 3, but `scripts/audit/check_knn_excluded_vision.py` failed all 3 (the host's
  Bats came back with 8 + 8 neighbours, the client's with 0). Run both peers with `-ffCombatFloatWitness` and
  that script: exit 2 means the run never exercised hide, then load, then un-hide, so its pass proves nothing.

**Mechanism.**

- `PlayerDisableFleetSystem` hides a combat ship with `PlayerShipDisabled` + `DisableKnnMarker` and
  leaves its vision alone (`PlayerDisableFleetSystem.cs:577-578`).
- `KnnSystem`'s vision query excludes `DisableKnnMarker` (`KnnSystem.cs:400`), so the buffer keeps
  the neighbours of its last refresh. `TargetingSystem` skips the ship too (`:97`), so a target
  that dies meanwhile stays in `Targeter`.
- `KnnEnemyVision` and `KnnFleetVision` are not saved. A joiner or a recovered peer has an empty
  buffer, and the save turns the dead target into `Entity.Null`.
- The un-hide goes through the pre-transform command buffer. `TargetingSystem`
  (`FFFixedPostTransformGroup`) runs later in that heartbeat, before `KnnSystem`
  (`FFFixedEarlyGroup`, `OrderFirst`) refreshes the buffer.
- The host clears the dead target and acquires from the stale list (`GetValidTargets` has no range
  check), so its Bats go to Chase. The loaded peer has no list and stays idle.

**Repro.** Nightly `W197-stale-vision-unhide`: 20 passive Bats visit a camp for 1.25 s, the player
leaves and the fleet hides, a client joins, the host flies back and the fleet un-hides. It forked
on `census` in 4 of 5 runs, on two Macs and on two unmodified 0.50.0.64 Windows players, with the
live report's signatures (`6056C9DE2D8482BD` Chase, `C6C13CE0C164D1D5` idle).

**How to recognise the class.** "X on the host only, long after a join" on one architecture is a
state gap, not float. Ask what unsaved state a long-running peer still holds for entities that are
excluded from the system that refreshes it, and which consumer reads it in the heartbeat the
exclusion ends. Check the command buffer that removes the marker against the consumer's group.

**Architecture facts measured the same night** (`-ffFloatConformanceProbe`, 62 operations, 2,048
samples each, `scripts/audit/compare_float_conformance.py`):

- The Steam Mac build runs its Intel slice under Rosetta. Player.log shows it: the Backtrace
  plugin fails with "have 'arm64', need 'x86_64'".
- Rosetta against Windows: every Burst operation bit-identical, a 64-body broadphase ray cast
  included. Only `UnityEngine.Quaternion.FromToRotation(...).eulerAngles.y` differs (up to 2 ulp),
  used at `LinearMotionSystem.cs:392`.
- Native arm64 against x64: scalar functions and `a*b+c` match (no FMA contraction). The float2/3/4
  forms of sin, cos, exp, pow, atan2 and acos differ by 1-2 ulp, and `quaternion.Euler(0, ±π/2, 0)`
  differs in every sample (`LinearMotionSystem.cs:400`, the avoidance slide). A native arm64 Mac
  player drifts from x64 peers there, and the fingerprint does not see mirrored rail poses.
- Managed (Mono) float results are identical on all three; managed and Burst differ from each
  other.

**Tools.** `-ffCombatFloatWitness <file>` (+ `-ffCombatFloatWitnessRegion x,z,r`) writes the bits
of every combat mover per heartbeat; `scripts/audit/compare_float_witness.py` names the first bit
that differs. A probe that reads a component outside its own query must complete tracked jobs
first, or it reads the previous heartbeat's value on some heartbeats and shows a difference that
is not there.

**The report could not answer it.** Its ship detail is cut at 512 KB and sorted by object id
(`FleetInputsDetail` 477 of 7,811, `MoversDetail` 64 of 7,818), so none of the forked Bats was in
it. The census signatures and the save the host served at the join (`*_served-*-e1.zip` in the
host's report) were what worked.

Related: [[join-load-route-provisioning-desync-class]], [[order-sensitive-vision-buffer-consumers-open]],
[[movers-detail-group-diff-and-float-mirror-flicker]].
