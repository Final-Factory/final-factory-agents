---
name: a-ui-change-leaves-the-rest-of-the-screen-as-it-was
description: "A UI change proves it left the rest of the screen as it was: a whole-screen layout census before and after (whole HUD showing, every slide-out open) with no new overlap between always-on HUD blocks, no anchored cluster drifting more than 2 px, and every touched panel's measured colour and alpha within reach of a classic panel's. A panel the player opens on purpose and can close may cover the HUD, if it draws on top, is clickable, stays on screen and gives the HUD back (Ben, w732 and w742). Checked by the released pr_evidence.py, not an older copy."
date: 2026-10-09
---

# A UI change leaves the rest of the screen as it was

**Rule.** Checking the panel you changed is not enough. Before a UI change is done, take the layout
census (`unity-ui`, `layout-census.md`) before and after, same save and size, with the whole HUD
showing and every slide-out open, and run `ui_layout.py check`:

- no new overlap between always-on HUD blocks, and none left between blocks you moved;
- every panel the player opens on purpose and can close (Blueprints, Inventory, the slide-out flyouts, the Station
  panel, the hub) may cover the HUD, and then must be **on top, fully visible and clickable, with nothing under it
  catching the clicks, inside the screen, and the HUD back when it is closed**;
- no anchored cluster (the minimap and its side buttons, the hotbar, the top bar) drifting more than
  2 px against its anchor;
- every panel you touched, measured on screen against a classic panel: delta E 10 or less, the same
  art, the same see-through.

**Ben's rule (w732 and w742).** Two corrections of the same kind, so it is in the checker now:

- "Put the slide out back just make it appear over the hot bar. The user can then close it to show the hotbar
  again" (Ben, w732, 2026-10-09).
- "the blueprint panel showing over objectives is fine since its a temporarily opened panel" (Ben, w742,
  2026-10-09, on the Blueprints window covering the Objectives card).

What passes: an opened panel over the hotbar, the Objectives card or the minimap buttons. What still fails: an overlap
between always-on HUD blocks (hotbar and minimap buttons, ability row and hotbar, Objectives and minimap), alignment
drift of an anchored cluster, an opened panel drawn **under** the HUD or cut off by the screen edge, one whose
clicks reach the HUD beneath it, one that leaves the HUD moved when closed, and a colour mismatch.

Paste its three lines into the PR. Run the released `pr_evidence.py`: a copy older than the
released one now fails itself.

**Why.** Two misses reached Ben on the night of 2026-10-08 (w733):

- **The rest of the screen.** On develop at 1280x800 the quick buttons stood off the minimap, and
  the Blueprint slide-out lay over the hotbar's 9 and 0 slots. Ben: "gotta remember this part of
  overlapping elements and also not breaking the layout". MEASURED (w733 layout censuses in the
  editor, 1280x800, UI scale 0.9, the classic layout, a new game):
  - #1264 (w644, merged as 121b8691b) moved the quick buttons from 7 to 24 px off the minimap frame,
    the slide-out toggles 31 px and the hotbar 98 px; from 121b8691b to develop 102e46bed nothing in
    that corner moved. `ui_layout.py check` fails #1264 at a 98 px drift. #1264 meant to pull the
    crowded pieces apart (Ben's "icons are still crammed by the minimap and hotbar"); the check would
    have made it show the move and the gap it left, and quote the words it answered.
  - #1264 merged at 20:29 UTC with no evidence-gate verdict, and its description fails
    `pr_evidence.py` of every version (no `Kind:` line, no claims table): the check was optional, and
    skipped.
  - Opening the Blueprint slide-out puts it over hotbar slots: a new overlap `ActionBarParent` x
    `QuckControls` (3948 px2) against the closed HUD, which has none. It is older than #1264 (at
    a42cc5a34 the same slide-out covers slots 8 to 0).
  - w732 named the commit: 7f75224fa (#1264's `HudCornerSpacing`). Alone it does nothing (its
    static initializer throws on `Debug.isDebugBuild`); with 099337640, the next commit of the
    same PR, it runs. 7f75224fa^ against 099337640: the same 98 px drift, and the slide-out over the
    hotbar shrinks from 14689 to 3948 px2 but stays, between the two blocks the change moved. A
    check that fails only new overlaps lets that through, so ui_layout.py (1.22.1) also fails an
    overlap kept between blocks the change moved.
- **The colour check that did not run.** #1272 (w712, the Blueprints window on the Deck) added a
  `SolidBackdrop` Image at `(0.05, 0.09, 0.14, 0.98)`, #0D1724 nearly opaque, where the game's
  windows use the translucent `background-main` sprite. MEASURED (`ui_layout.py check`, censuses and
  stills at 1280x800 of #1272's base 121b8691b and its head 3b807f9bf, against the classic Inventory
  on screen): the window was delta E 2.1 from the classic panel before, 23.8 after; the check fails it. Why the w718 check
  (ff-agents 1.21.0) did not catch it:
  - MEASURED: 1.21.0 was released at 21:53 UTC. #1272 opened at 22:43, and its "evidence-gate:
    PASS" comment was posted at 22:47. 1.21.0's `pr_evidence.py` fails #1272's description on 5
    counts (no `Content:`, `Full content:`, `Style:`, `Shots:` or flicker result); 1.20.44's
    passes it. The PASS came from a copy older than the release. The worker began
    w712 at about 20:54, before the release, and a session loads its plugins when it starts. GUESS:
    whether m5 had 1.21.0 installed at all by then.
  - MEASURED: even 1.21.0 would have accepted a sentence as the `Style:` line, and #1272 already
    had one ("the panel keeps its translucent look"). Its colour tool, `ui_check.py style`, needed
    two hand-picked rects, and nothing made anyone run it on each touched panel.
  - SOURCED: w712's brief offered "a deliberate full-screen modal with a solid enough background";
    Ben never asked for a new colour, and nothing compared one with the game's panels.

**How the rule got here.** w733 counted every overlap as a defect. Ben's words in w732 were that the slide-out
panels "still intersect with the hotbar"; w732's brief turned that into "0 overlapping HUD element rects", the worker
moved the slide-outs above the toggles, and Ben corrected it with the first quote above. w732 then hard-coded the one
pair (an open slide-out over the build bar), and `ui_layout.py` 1.23.x got a one-pair `byDesign` entry in
`hud-clusters.json`. Then w733's own demo flagged the Blueprints window over the Objectives card on #1272, and Ben
answered with the second quote. A pair-by-pair list was the wrong shape: the rule is about *what kind of thing* is on
top. Since w742 (`ff-agents` 1.24.0) `hud-clusters.json` classifies elements (`openedPanels.paths`: slide-outs, the
windows, the structure panels, the Station panel, the hub; everything else is always-on HUD), `byDesign` is gone,
and `ui_layout.py` checks the opened panel instead of exempting it (`Opened panels:` line). MEASURED (the tests,
`unity-ui/tests/test_ui_layout.py`, on the rects the w733 censuses recorded): the Blueprints window over the Objectives
card is 0 new overlaps, and #1272's navy window still fails the colour (the stills are synthetic, set to the measured
on-screen gap: delta E 23.8, 2.1 before); #1264's minimap drift still fails at 22 px on the buttons and 98 px on the
hotbar block. Limits: the census sees only what draws, so an invisible raycast catcher under a panel needs
the event-system probe (#1287's `DeckTour` counted 66 of 66 click points reaching the panel); a window that is
not on the `openedPanels` list counts as HUD until someone adds it, which is deliberate (a new always-on element must
not be waved through by name).

**A third correction in the same corner (w732, 2026-10-09).** After the two above, the fix for "the minimap buttons ...
no longer hugging the minimap nicely (with a little padding), ... not quite aligned" also spread the button columns over
the minimap frame's height, because the brief wrote "top and bottom edges aligned with the minimap frame" and the test
pinned it. Ben: "I don't want the minimal icons to fill the vertical space. I want them to stack with a little padding like
before. I dont like how the left most row is separated vertically in between each button." The check that would have caught
it is [ui.md](../checklists/ui.md) item 1: only the person's words are targets, and "like before" means the measured *before*
still; `HudCornerLayoutTest` now pins the 6.5 gap and an even padding of at most 7 units between buttons (measured: 14.1 and
32.1 in the stretched scene, 5 as the scene lays them out), and fails the stretched scene.

**How to apply.** [The UI checklist](../checklists/ui.md), items 11 to 14, and the `unity-ui`
skill's `layout-census.md`:

- Census before and after with the whole HUD up and every slide-out open, and one more with your panel closed
  again; `ui_layout.py check --touched <your window> --closed closed.json --shot after.png --ref-shot <classic still>`.
- Paste its `Overlaps:`, `Opened panels:`, `Alignment:` and `Style:` lines. `pr_evidence.py` fails a UI PR without
  them, with a new overlap, a drift over 2 px or a delta E over 10, unless the line quotes the
  requester asking for it: `intended (Ben): "..."`. An opened panel under the HUD, not clickable, cut off or not
  restored fails with no `intended` way out.
- Run it yourself before every UI merge and post its verdict (`--comment`); nothing in CI runs it
  yet (w733: a job is written, waiting for someone whose token may push workflow files).
- When a check changes mid-task, re-register (`registerAgents.sh`), restart, and run it again before
  merging. `pr_evidence.py` names its version in its verdict and fails when GitHub has a newer one.
