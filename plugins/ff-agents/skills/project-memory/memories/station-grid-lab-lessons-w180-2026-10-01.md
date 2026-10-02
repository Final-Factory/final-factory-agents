---
name: station-grid-lab-lessons-w180-2026-10-01
description: "What the w180 station-grid work (BEAST, 2026-10-01/02) taught about testing stations in built players: blueprint.place re-runs the grid calculation inside the current heartbeat and doubles that phase's sums; a Repair Center draws power when armor is hit; destroyed structures leave ghosts a bot rebuilds; a cut-off piece is a station of its own; an agent command runs mid-frame, so compare builds on rows sampled at the end of the frame."
metadata:
  type: project
---

# Station grid lab lessons (w180, PR 916, 2026-10-01/02)

Source: the `SP-station-change-no-flicker` / `MP-station-change-no-flicker` scenarios, the
`station.powerwatch` command and `scripts/audit/run_station_structure_change_audit.sh`. Record:
game repo `specs/w180-station-power-no-transient/README.md` and `proofs/verification.md`.

**1. Never add a structure to a station under watch with `ffauto:blueprint.place`.** It builds at
once and calls `SaveGameManager.RunAllSystemsToInitializeGameWorld` (`TestModeInitializer.SetupBlueprint`),
which runs `StationGridCalculationSystem` a second time inside the current heartbeat. Whatever that
`hb % 8` phase sums is doubled until the next publish: on phase 2 the overdriver bonus read 0.5 instead
of 0.25 and the exploration radius 21 instead of 17.5, for eight heartbeats. It looked like a bug in
the change under test and was the harness. Place with `ffauto:construction.placeitem|<item>|<x>|<z>`
after `ffauto:inventory.add`, and let a Construction Bot build it (single player: craft one;
multiplayer: `ffauto:spawn.ships|Construction Bot|1` on the host). Both go through the operation
queue, so a client sees them. `blueprint.place` is still right for the fixture built before the
watch starts.

**2. A blueprint encoded by `make_blueprint.py` carries a `Version`,** so nothing rotates its Command
Core on load: on the Station Core's north edge it takes no `dir`. A version-less blueprint string
(the older `.ffbp.txt` files) gets its command cores rotated by `BlueprintCompatibility`, which is
why those use `dir` 2. Copying the `dir` from an old file built a one-structure station.

**3. Fixture behaviour that reads as a bug.**
- A Repair Center draws extra power while anything on its station is damaged. Left standing, an
  armor hit becomes a real, short power dip. Destroy it first in a scenario that asserts no dip.
- A destroyed structure leaves a ghost, and a bot rebuilds it as soon as the player holds the part.
  A block deconstructed by a bot goes into the inventory and may go straight back onto an earlier
  ghost of the same item. To rejoin a cut station, hand the player a Strut.
- A piece cut off a mobile station becomes a station (Hauler) of its own
  (`MoveableStructurePostConnectionSystem`), so `any|any` selectors fail with "found 2" after a
  split. Name the station by its Command Core tile.

**4. Comparing two builds on one save.** An agent-channel command runs mid-frame, before or after
that frame's simulation step, and it varies from run to run. A dump labelled with the heartbeat
counter is therefore one heartbeat off at a publish boundary in some runs: two builds that agree
looked different on `hb % 8` of 5, 7 and 0. Sample at the end of the frame
(`await UniTask.Yield(PlayerLoopTiming.PostLateUpdate)`, as `station.powerwatch` does) and pair rows
by heartbeat. Done that way, Ben's 11,252-structure battleship gave 643 identical rows of 643 on the
old and the new grid code.

**5. A local "before" player without switching branches.** `build_player.sh` needs a clean tree at
the sha it is given. Commit the reverted files locally on the working branch, build, then
`git reset --hard` back to the real head, and do not push in between. Remove tests that need the
new code from that commit, or the batchmode build fails on the test assembly.
