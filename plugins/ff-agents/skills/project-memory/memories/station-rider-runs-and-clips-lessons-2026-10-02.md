---
name: station-rider-runs-and-clips-lessons-2026-10-02
description: "w165 (two players on one mobile station; #915, #910, #936; recorded on BEAST): build a test station by save, not blueprint.place; a player's window size comes from saved display settings; park the pointer; a player answers one command chain at a time; the probe reads matrices and misses a culled frame; build_player.sh restores tracked files; a camera that follows the station makes a model call the clip static; a 'ship slot' read from FleetCommander.FleetPosition is one station step old."
metadata:
  type: project
---

# Two players on one station: recording, probe and review lessons (w165, 2026-10-01..02)

PRs #915, #910 and #936 in the game repo. Runners and analyzers: `scripts/feel/README.md`, "Two players on one
station". Write-ups: `specs/mp-station-riders/`.

## Setting the scene

- **Build the test station once and load it from a save.** `ffauto:blueprint.place` (the test-mode instant build)
  draws a station out of place on the peer that placed it. Build it with a host playing alone, `ffauto:game.save`,
  and start the runs with `-ffAutomationSave`.
- Several clients on one machine each need `-ffAutomationReclaimIdentity`, or the second supersedes the first.
- A host's pre-connect chain is still running after `status pre-connect-command-complete`: retry on `rate_limited`.
- **A player answers a command chain only between its own chains.** To read where the station is while one player
  drives it, ask the player that is not driving.

## The window and the pointer

- A player's window takes its size from the machine's saved display settings (shared PlayerPrefs), not from
  `-screen-width`: 1280 x 720 on BEAST. Do not change the shared setting; scale the saved frames instead.
- **The game hovers whatever the desktop's cursor is over.** A hover panel or an outline then sits in every frame.
  Park the pointer first: `ffauto:pointer.moveto|30|620|screen`.
- The probe's screen positions are the camera's pixels (3840 wide on BEAST), not the window's.
- Two players, each saving every frame at 960 x 540, hold 46 to 59 fps on BEAST. Three at 1080p ran at 13 to 38 fps:
  those clips show what is drawn, not how smoothly.

## What the probe does and does not see

- **The probe reads matrices.** A ship whose matrix is back in place but which is culled for one frame (its render
  bounds still held the parked model) looks drawn to the probe. Check the pictures for "is it visible"
  (`check_rider_look_clips.py`), and the probe for "where is it".
- **`FleetCommander.FleetPosition` is one station step old while a station flies** (it is sampled in the fixed
  pre-transform group, before the station's movers land). A "distance from slot" computed from it shows 3 to 4.6 u
  for a ship that is exactly on its slot. Take the slot from the platform's own simulated position in the same
  frame (the `ship place` column of `analyze_station_riders.py`).
- Ships flying home are idle by state before they are docked. A "parked ships" statistic that filters on the idle
  flag alone includes them (13 to 20 u in the fight legs).

## Reviewing the clips

- **A camera that follows the station makes the station stand still on screen.** The blind model review called two
  such clips "static" and "stationary" while the station flew at 73.8 u/s. Say in the brief that the camera follows
  the rider and the background moves, and check the speed in the probe.
- A unanimous "Ship it" is not the end. Stepping the frames of a turn on the client's screen found a 4 u sawtooth
  of a parked ship against its platform, once per heartbeat, that no review named. Look at the peer that receives
  its heartbeats over the network, and at turns: straight flight hides it.
- Compare what another player sees of a player with what the player sees of themselves before calling a visual fix
  done (#884 put a remote rider's ship on the seat; the rider's own game hides it).
- Cut clips with real-time timing on a fixed 60 fps grid (cumulative timestamps, not per-frame rounding: per-frame
  rounding played 17% slow), and give each clip a lead-in so its event is not on the first frame.

## Builds and long runs

- **`scripts/nightly/build_player.sh` restores every tracked file that changed while it ran.** Commit first, and
  do not edit tracked files during a build. New untracked files survive.
- It needs the editor stopped, a clean tracked tree and `HEAD` equal to the sha it is given.
- From Python on BEAST, call `C:/Program Files/Git/bin/bash.exe`: plain `bash` resolves to WSL.
- When develop moves under a simulation pull request that is already recorded, merge it, build that head and run
  one paired audit and one recorded session again before merging (#916 changed the station grid's systems between
  the recording and the merge of #936).
- A session interrupted by an app restart leaves its batch dead and its run folder half written: make every batch
  skip what has an `ok` marker and start it again.
