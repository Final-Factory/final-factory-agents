---
name: hover-and-tooltip-audit-world-and-tour-traps
description: Auditing hover cards and tooltips with the Deck tour (w714): a loaded copy of every structure through the one-item blueprint's DevSlotData, the Burst abort when a structure has no inventory, one tour player at a time, the camera settle after a layout switch, tooltips counted before they are placed, the crash that leaves a batchmode Unity holding the lockfile, and measure the before before writing the fix.
---

# Hover and tooltip audits: world, tour and measuring traps

Learned on w714 (2026-10-08/09, m5), 85 structures x empty/loaded x two layouts x two sizes, plus a tooltip sweep.
Scripts: `scripts/deck_audit/` (`build_audit_world.py`, `build_loaded_world.py`, `make_hover_tour.py`,
`make_tooltip_tour.py`, `make_world_tour.py`, `hover_summary.py`, `summarize_tooltips.py`); census in `DeckTour.cs`
(`cards`, `hoverSweep`, `worldSweep`, `census:`).

## A loaded structure: DevSlotData, only where the inventory exists

`ffauto:blueprint.place` with a one-item blueprint whose `DevSlotData` holds the stacks (and `DevSlotNames` the item
names; a name wins over the id on paste) puts items into a structure. The instantiator indexes `DevSlotData` by the
prefab's own slot count, so give it more entries than any structure has (600; 40 crashed on a Large Cargo Hold:
`IndexOutOfRangeException ... Length 40`, a Burst abort that ends the player). A structure with no `InventorySlot`
buffer aborts the player too (`AppendRemovedComponentRecordError`, an Advanced Solar Panel): place loaded copies only
where `observe.state|structure|x|z` of the empty copy has an `"inventory"` key (43 of 85).

## One tour player at a time

A second player started beside a running tour (another slot, `--peer`) never reaches "Select Research": its tour
sits at step 0 for 600 s. Queue tours; do not run them in parallel. Stop the previous player by its pid before the
next one, or two tours write into one out folder.

## Camera follows the player at a limited speed

After a `layout` step and a 330-tile `player.setposition`, the next 57 `pointer.moveto` steps all failed with "projects
behind the camera". Teleport next to the first target and `wait 20` before a pass; the same after jumping between the
empty and the loaded rows. A hover shot whose cursor missed the structure has no card: also take its `ui.selecttile`
shot, and read "no card" as a missed hover, not as a missing card.

## Do not count a tooltip that is not placed yet

`CreateTooltip` parks a tooltip at y 999999 until the tooltip delay has run. On a busy machine (a Burst build running)
28 of 36 tooltips of one run were still parked when measured and read as "off screen". Check the rect's y is under about
5000 before counting a tooltip, and run a before/after pair on a quiet machine.

## Measure the before before writing the fix

The tooltip clamp was written first; the sweep with it switched off (`-ffNoTooltipKeepOnScreen`) then showed that every
sampled tooltip (325 in 16 states) already fit at 1280x800: the existing flip is enough there. The hover card, by
contrast, was 26 of 43 off the top. Take the before from the same tour on the base build first, so effort goes where the
numbers are.

## Other traps met

- A python edit that asserts the old text and then writes the unmodified string is a silent no-op: the census rule never
  landed and a whole tour ran with it missing. Grep the file after every scripted edit.
- A tour's UI scale and layout change the numbers; compare before and after at the same scale (w727 made 0.80 the Deck
  default after the "before" build).
- A batchmode build that crashes (a `mono_crash` file in the checkout) can leave Unity running with `Temp/UnityLockfile`
  held, and the next `build_player.sh` says "refused: an editor holds ...". `mcp__machine__unity` action `restart` with
  `force: true` removes the stale lock; killing Unity by hand is blocked. See also
  [the stale lockfile](stale-unity-lockfile-after-sandbox-editor-stop.md).
- `mcp__machine__switch_branch` pushes the branch you leave if it has unpushed commits; a temporary branch you switch
  away from ends up on origin, and deleting a remote branch is blocked in a sandbox.
- `ui_layout.py check` needs the layout census JSON (the `census:<path>` tour step, or the editor snippet) of a base
  build and of yours, taken the same way; `pr_evidence.py` wants its `Overlaps:`, `Alignment:` and `Style:` lines
  verbatim, the word "flicker" in the value of the `Clips:` or `Flicker:` line, and refuses to PASS an old plugin version:
  update the plugin and run the newest copy (`sort -V`). `--comment` posts a FAIL as readily as a PASS.
