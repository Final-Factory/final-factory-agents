---
name: ui-canvas-rebuilds-every-frame-census-the-queues
description: "A window that makes the UI canvas rebuild every frame may not be the culprit: on Wittlebase the inventory's +1.6 ms came from the faded-out hover card, whose scale LateUpdate and a render-time hide flipped 1->0 every frame. Count uGUI's rebuild queues in the bench player (-ffBenchCanvasDirty 1) before changing the window; hold one window open with -ffBenchHold; IndexedSet queues throw when enumerated."
metadata:
  type: project
---

# A canvas that rebuilds every frame: count the queues first (w2392, 2026-10-27, BEAST, PR #2716)

The request (lothsahn, via the orchestrator): "while the inventory window is open it adds about 1.6 ms to every frame,
because its UI canvas rebuilds every frame". The inventory was not the cause. Its slots queued work only on frames
where something changed.

The cause was in `HoverCardFit` (`Assets/Scripts/UI/Panels/HoverInfo/HoverCardFit.cs`):
- `LateUpdate` gave a faded-out card (its canvas group alpha ≤ 0.001) its design scale back.
- `HideUnderAWindow` runs at `willRenderCanvases` through `HudUnderWindows.Rendering`. It set the scale to 0 because a
  window covered the card.
- So the scale went 1 → 0 every frame a window was open. On the shared pixel-perfect "UI Canvas" (2415 graphics),
  each flip re-laid out `HoverDescription/Parent` and rebuilt its images.

**The rule.** When two code paths write the same RectTransform scale or size in different phases of one frame
(LateUpdate against a render hook), the canvas is dirtied again every frame, even while the element is invisible.
The fix was to skip the render-time hide while the card is faded out.

## How to find the culprit

1. **Hold one window open in the bench player.** Run `scripts/bench/roam_hitches.sh <exe> <out> <save> -ffBenchHold
   inventory:60 -ffBenchObelisk 0 -ffBenchIdleStart 20 -ffBenchIdleEnd 0`. It gives a `hold-closed` phase, then a
   `hold-inventory` phase opened with `ffauto:ui.open`, each with its own p50 and p99 in `summary.txt`.
2. **Count the rebuild queues.** Add `-ffBenchCanvasDirty 1`. Per frame it counts `CanvasUpdateRegistry`'s layout and
   graphic queues and logs the entries that come back most often, by hierarchy path. Before the fix, 2541 of 2541
   open frames had something queued, and the top entries were the hover card (5078 layout, 2539 per image). After the
   fix, 1217 of 2615 frames had something queued, and the hover card was gone.
3. **Get the markers.** Add `-ffBenchSystems 1 -ffBenchProfile 1` in a development player. Then run
   `ExcessReport.Batch -exByMarker "InventoryPanel.Update() [Invoke]"`, which splits the open frames from the rest.
   Measured: CanvasUpdate.Layout went from 0.33 to under 0.002 ms, and PreRender from 0.25 to under 0.002 ms.
4. **Stills.** `-ffBenchHoldShots "Iron Ore:50"` takes a still of the held window. It then adds the items with
   `ffauto:inventory.add` and takes a second still, which shows the count change is still drawn.

## Traps

- `m_LayoutRebuildQueue` and `m_GraphicRebuildQueue` are `IndexedSet`, and enumerating one throws. Index it through
  `IList` (Count and the indexer) instead.
- A `Canvas.preWillRenderCanvases` probe added in the editor broke the editor. Probe in the bench player.
- On Windows, `roam_hitches.sh` takes the save as a bare name that is already in the game's saves folder on C:. A path
  on another drive (F:) failed with DirectoryNotFound.
- Not everything an open window costs is a rebuild. After the fix about 1 ms remained, per open frame:
  ClipperRegistry.Cull 0.19, CraftingPanel.Update 0.15, HudUnderWindows.CollectWindows 0.15, InventoryPanel.Update
  0.09, plus about 0.3 ms of GPU. Those are per-frame scripts and drawing, not the canvas.
