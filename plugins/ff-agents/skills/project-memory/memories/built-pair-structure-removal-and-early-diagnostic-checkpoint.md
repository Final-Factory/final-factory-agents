---
name: built-pair-structure-removal-and-early-diagnostic-checkpoint
description: "Built-pair lab facts from the 073 orphan/breadcrumb legs: `ffauto:construction.remove|x|z` resolves ONLY the ground tile and completes only with construction bots + the player in action range; a chain whose endedHeartbeat is lower than its startedHeartbeat crossed a desync recovery; for a CensusDetail leg block on the first DesyncRecoveryAttempt and checkpoint at once instead of waiting out the leg; a 'same shape' leg can differ silently (windowed host: the beam mined nothing) — check the action's effect, not the chain status; hazel1831 commander inventory."
---

# Built-pair structure removal, and the early diagnostic checkpoint (073, 2026-09-17)

Lab: `/private/tmp/ff073-hazel-20260915/xplat/` (`run-g9.sh` takes `LEG=`, `nearby_dp.py`, `censusfirst.py`).
Companions: [[built-pair-lab-traps-073]], [[agent-control-chain-fifo-and-mining-startnearest]].

1. **Removing a structure from the harness.** `construction.remove|<x>|<z>` resolves only the ground tile
   `(x,0,z)` (`LocalMultiplayerAutomationCommandRunner.ResolveConstructionRemoveTarget`), so an Inserter Bot
   at `y = 1` cannot be targeted. The Unbuild op only stamps `ConstructionTaskData{RemoveStation}`; the
   structure is deleted when the requesting player has construction bots enabled, stands within
   `Player.ActionRange / 10` tiles and has an idle bot (`ConstructionTaskAssignerSystem.cs:255-311`). A
   `MarkRemoval` with no bots sat pending for 2,400 heartbeats. Leg chain that works:
   `spawn.ships|Construction Bot|4; wait|2; movement.goto|<wx>|<wz>|40|150; wait|3; construction.remove|x|z`.
   `fleettransfer.take|<ship>|<n>|<x>|<z>` frees slots in a neighbouring commander (for orphan contention).
   `snapshot/nearby` lists a structure by its lower-left tile, not its `CenterTile`.
2. **`endedHeartbeat < startedHeartbeat` in a chain result = a session reset (desync recovery) happened
   mid-chain.** Read the host log for `DesyncRecoveryAttempt` before trusting anything the chain did.
3. **Early diagnostic checkpoint.** With `AuditCaptureProfile: diagnostic` + `CensusDetail`, do not wait
   out the leg: `until grep -ac DesyncRecoveryAttempt host-terminal-<leg>.log ≥ 1`, then `cp.sh <leg>
   <label>` at once. Both reports then hold the whole pre-recovery epoch (59 MB each for 673 hb of
   `hazel1831`) and `censusfirst.py HOST CLIENT 1` names the differing rows. ~2 minutes per iteration.
4. **"Same shape" legs can differ silently.** On a WINDOWED host `mining.startnearest` reported completed
   but the beam mined nothing (ore 20 → 6 from the two Miner Bots, then stuck on both peers), so leg g6
   proved the census strip set under rendering but not the deletion heartbeat. Check the action's EFFECT
   in the poll, not the chain status. Cause not diagnosed.
5. **`hazel1831` inventory.** 3 players, 35 placeable fleet commanders: 11 Defense Platforms × 20 Bats
   (centre tiles (16,0,4), (21,0,10), (25,0,10), (-20,0,12), (5,0,-26), (1,0,-26), (90,0,9), (94,0,9), …),
   Mining Stations × 4 bots, Ship Yard (2,0,-34) 45 ships. Every structure of the base is within 15 tiles
   of a Defense Platform, so any leg that walks a player into the base trips T029
   ([[per-peer-gates-on-structural-changes-fork-the-census]]) until that is fixed.
