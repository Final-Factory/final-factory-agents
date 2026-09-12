---
name: placement-and-grid-attachment-from-the-harness-r15
description: "Harness placement facts proven on lane r15 (windowed M5 host): a structure's GridTile is its LOWER-LEFT footprint tile; a Solar Panel joins a station grid only through its direct-connection slot (RequiredSlotsForDirectConnection), never by adjacency — place it Up one column left/one row below the slot, then rotate.abs 3 then 1 (a 1×2 panel's anchor moves on rotation; a colliding rotation is rejected); attach diamonds show while armed; ui.click's result never proves the item armed (screenshot 2-3 s after pointer.moveto); a stray built panel is refunded by construction.remove; observe.state nearby needs radius ≥ 20 to see an asteroid."
---

# Placement and grid attachment from the harness (2026-09-12, 069 lane r15, windowed M5 host 1280×800)

- **GridTile = lower-left.** A 3×2 Mining Station reported at tile (-43,-16) covers x -43..-41, z -16..-15;
  the base station at (-5,-58) covers x -5..-3, z -58..-57 (`observe.state|nearby` + screenshots, 069 plan
  17:15 block). Aim `pointer.moveto|<x>|<z>` at the tile you want as the anchor, not the centre.
- **A Solar Panel attaches only through its direct-connection slot.** Dropped merely NEXT to a station it forms
  its own grid (`satisfaction 1 / drawNeeded 0 / stability needed 2` while the station stays `sat 0`) and the
  tutorial objective does not complete; the join is decided by
  `StationConnectionsSystem.HandleDirectConnection` (`StationConnectionsSystem.cs:374`) against the config's
  `RequiredSlotsForDirectConnection` (`:618`). What worked every time: place the panel with the default Up
  rotation one column LEFT and one row BELOW the target slot, then `rotate.abs|x|z|3` then `rotate.abs|x'|z'|1`
  — a 1×2 panel's anchor MOVES on rotation (Up at (a,b) → Right at (a−1,b+1)); the Right-facing panel's +x end
  lands on the station's left column and the station's `satisfaction` jumps. A rotation whose footprint
  collides is `rejected`. Green diamonds around a station while an item is armed mark its attach slots; a
  ghost snapped to one turns red when its footprint overlaps another structure.
- **Arming is proven only by a screenshot.** `ui.click|inventory|InventoryPanel/Content/Inventory/item-slot(Clone)[item=X]`
  returns a string truncated at "the EventSystem raycast decides delivery" whether or not the item armed; the
  item usually IS armed — take the shot 2-3 s after `pointer.moveto|<tile>` (green ghost + "Save New Blueprint"
  bar) and do not repeat the click. A structure placed from the inventory on a free tile is BUILT at once.
  A "Technology Unlocked" modal blocks placement: Dismiss at native `1284|668`
  (`pointer.moveto|1284|668|screen` + `pointer.click|0|3`).
- **Undo:** `construction.remove|x|z` on a stray BUILT panel refunds it to the inventory. Bot paths (an
  Inserter Bot placed by a click) are not structures — `construction.remove`/`deleteimmediate` reject them.
- `observe.state|nearby|x|z|r` with r = 8 missed an asteroid 10 tiles away; use r ≥ 20 for terrain.
- Related: [[headless-windows-player-over-ssh-and-placement-route]] (the route + its three blockers),
  [[tutorial-map-fleet-complete-automation]].
