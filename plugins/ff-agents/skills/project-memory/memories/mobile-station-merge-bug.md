---
name: mobile-station-merge-bug
description: "Root cause of stations merging when landing (BugReport_20260720_164112) — landing checks are overlap-only vs EntityMap, flying stations absent from map, contact unions grids, undock flies the whole union"
metadata: 
  node_type: memory
  type: project
  originSessionId: bfe6f575-91b6-4688-b1af-8fbc2521cbcc
  modified: 2026-07-21T07:38:27.108Z
---

Bug report BugReport_20260720_164112 (user save, v0.20.0.115, no mods): three identical
cargo shuttles on a "Matrix Baux" ↔ "Matrix Baux Mfg" route merged into ONE 102-item
StationGrid (3 Small Command Cores → one Hauler 48045), stacked at 8-tile z offsets, some
items on identical tiles. Verified live 2026-07-20 by loading the save in the editor
(`Serialization.SaveGameManager.LoadGame("<name>", true)` via execute_code — bug-report
zips sit directly in the saves folder and load by filename): the whole blob undocks,
flies, and re-lands as one station, re-stamping all 102 GridTiles around each pad.

Root cause chain:
1. ALL landing protection is overlap-only against FFGrid.EntityMap
   (`MobileStationUtils.IsAnythingInTheLandingZone`, manual-land ghost
   `BlueprintPlacementSystem.AnyInvalidPlacement`). Flying stations are NOT in the map
   (tiles removed at liftoff in `MobileStationUndockingSystem.RemoveStationGridItemsFromMap`),
   and a landing station enters the map only post-touchdown (`StationDockingMarker` →
   `MobileStationGridUpdaterSystem`, Late ECB). Two stations descending on overlapping
   footprints pass every check.
2. Per-pad queue serializes only automated docking; temporary (manual move/land) stops
   bypass it (`MobileStationQueueSystem` IsTemporary branch). Manual ghost check happens at
   click time, seconds before touchdown.
3. Adjacency is legal; on landing `StationConnectionsSystem` connects everything adjacent,
   and `StationGridMembershipSystem` makes grid == connected component → contact merges
   grids.
4. `MoveableStructurePostConnectionSystem` then DESTROYS the extra haulers and repoints
   all HaulerReferences to one survivor — cementing the merge.
5. Undock flies the ENTIRE StationGridItem buffer; `MobileStationDockingSystem.UpdatePlaceable`
   rewrites every item's GridTile per landing → stacked copies persist/propagate.

Also found: turning a hauler OFF mid-flight strips its state component permanently
(undock exit path when !IsOn); station hovers stateless forever (two "Silica" shuttles in
this save, IsOn=false, no *State component, frozen at y≈25). Only a manual command
(RemoveAllMobileStationStates + UndockingState) revives them. STILL UNFIXED as of
2026-07-21.

FIX (2026-07-21; verified landed on `master` 2026-08-01 — `MobileStationUtils.cs` carries
`TryClaimLandingZone`): Ben confirmed adjacency merges are
INTENDED; only overlap landing is the bug. Implemented landing-footprint claims: a docking
station claims its computed landing tiles in the EntityMap at the RotateIntoPosition→Dock
transition (`MobileStationUtils.TryClaimLandingZone`, docking job now single-threaded
Schedule + [NativeDisableContainerSafetyRestriction] EntityMap for atomic deterministic
check+claim), re-claims idempotently each descent frame (survives save/load mid-descent;
`AddPlaceableToGrid` made idempotent for same-entity re-adds),
`IsAnythingInTheLandingZone` now ignores the station's own grid items. Hauler merge made
deterministic: `MoveableStructurePostConnectionSystem` picks the bottom-left-most command
core (GridTile z then x, int math) with a valid unused hauler. Tests:
Tests/Haulers/HaulerLandingClaimTest.cs + MergedStationsKeepBottomLeftMostCoresHauler in
MoveableStructurePostConnectionTest.cs; all 420 FFEditorTests pass. Gotcha: test fixtures
using MobileStationDockingSystem must GetOrCreateSystemManaged<FFLateBufferSystem> or the
RequireForUpdate silently skips the system.
