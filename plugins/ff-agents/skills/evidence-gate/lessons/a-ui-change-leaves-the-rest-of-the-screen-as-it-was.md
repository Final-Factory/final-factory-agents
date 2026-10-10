---
name: a-ui-change-leaves-the-rest-of-the-screen-as-it-was
description: "A UI change proves it left the rest of the screen as it was: a whole-screen layout census before and after (whole HUD showing, every slide-out open) with no new overlap between always-on HUD blocks, no anchored cluster drifting more than 2 px, and every touched panel's measured colour and alpha within reach of a classic panel's. A panel the player opens on purpose and can close may cover the HUD, if it draws on top, is clickable, stays on screen and gives the HUD back (Ben, w732 and w742). Move only what the person asked to move: every moved element at 1920x1080, 1280x800 and 1280x800 docked is listed and asked for in the brief's own words, or put back, and the places Ben fixed himself (hud-pins.json) hold in every census (Ben, w826 and w894: \"stop moving panels around that I don't ask you to move around\"). Checked by the released pr_evidence.py, not an older copy."
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

## The other screen too (w761, 2026-10-09)

**Rule.** A UI change made for one screen (the Deck) is checked on the others (desktop 1920x1080 and 2560x1440 at
the default UI scale) before it is done, with the same whole-screen census, and with a per-text comparison when it
changes font sizes. A layout rule or a text size has no screen in it unless the code gives it one.

**Why.** #1282 ("classic Deck layout", w723/w727) was checked at 1280x800 and passed there. It also raised about
300 texts from 14 to 15/16 pt on every screen and made the classic packer place the player's own Inventory and
Crafting windows on every screen. The nightly regression check (w761, MEASURED in editor censuses, before
4762a5bc3 vs develop ca58de9c8): on desktop the Mass Driver's filter labels broke mid-word ("Component / s"),
Blueprints showed "Rename fold...", Mods' "Game Version" took two lines; the I-key Inventory moved to the left edge
at 1920x1080, the two windows swapped sides at 2560x1440, the Inventory jumped 317 px when the mouse crossed a
building (the hover card's soft zone grew) and Crafting opened under an Inventory the player had dragged. The PR's
own "Not verified" line had said "desktop text is 1 point bigger where it was 14": nobody compared what that did.
The labels fitted in the font their prefab names (Liberation Sans) and not in the one the game draws them in
(`LocalizationHelper.ApplyFont`: Khyay).

**How to apply.** `checklists/ui.md` items 15 and 16; `unity-ui` `text_diff.py` for the per-text comparison; in the
game repo, `SelectionColumnPanelsTests` pins which screens the packer places the player's windows on and
`RaisedLabelsFitTest` lays labels out in both fonts.

## Nothing moves that the brief did not ask to move (w826, 2026-10-10)

**Rule.** A UI change lists every HUD element it moved, at 1920x1080 and at 1280x800, and each one is either asked for in
the requester's own words, for that element on that screen, or put back. A move kept without being asked is named in the
report's first lines, with why.

**Why.** Ben corrected the same kind of miss twice in two days, both in the classic layout's top-left corner:

- 2026-10-09, on w722/w723: "you did more with the overall layout than i wanted. like the station controls are not being
  put above objectives. that's not what i wanted. objectives are on their own layer and game Ui panels should just show
  over top of them". Ben's words in w722 were "for the station controls panel just put in the top left corner and have
  the main panel and inventory position around it"; the note that carried them added "Mind the top-left HUD (the health
  bar and the objectives) so nothing overlaps", and #1280 moved the objectives card down under the strip
  (`KeepObjectivesOff`; w722's log: "the Objectives panel moves down under the strip and the two never overlap").
- 2026-10-10: "why is station info at the top left? i didnt tell you to move that". #1282 (w723) moved the Station Info box
  from above the ability row to beside the strip, on every screen. Ben's words in w723 were "we need a new place for Station
  Info hover panel thing it takes up too much space in the steam deck ui": a Deck request that named no place. The
  note that carried them added "It is the same on desktop unless that looks worse there"; the worker picked the top left
  and applied it to the desktop as well.

In both, the move came from a brief's own words around Ben's quote, which item 1 of the checklist already says are a
guess until the person says them.

Both PRs passed every check of their day: overlaps, cluster drift and colour look at what touches what, not at what moved.
#1282's TL;DR even said "a two-column Station Info box beside them", and nothing compared that with Ben's words. MEASURED
(w826, editor censuses of develop 4762a5bc3 and 102e46bed, #1282's merge, the classic layout, a new game with the tutorial
objectives and a selected station): `ui_layout.py moves` lists `GamePanels/BuildInfoPanel` at x -312, y -736 px at 1920x1080
and x -30, y -476 px at 1280x800, the first of 7 lines (the others: the strip's buttons and the hover card grew with the
text floor w727 asked for, and the Player Inventory moved 23 px at 1280x800). With Ben's Deck quote on both Station Info
lines, `pr_evidence.py` fails the 1920x1080 one: a Deck request does not move the desktop.

**How to apply.** [The UI checklist](../checklists/ui.md), item 22: `ui_layout.py moves` over both sizes, the `Moved:`
line and its list in the PR, each line marked `asked (who): "their words"` (since w894 there is no "justified": see below), and
`pr_evidence.py --brief <the brief>` so each quote is checked against the requester's words. "A new place" asks for a
move, not for the place you chose: put the place in the TL;DR for the person to see. The recorded censuses are
`unity-ui/tests/fixtures/w826-1282-*.json`.

## Move only what the person asked to move: the hard rule (w894, 2026-10-10)

**Rule.** Never move, re-anchor, restack or regroup an existing panel, HUD element or hover panel unless the brief quotes
the person asking for that exact element to move. A layout change touches only what was asked. There is no "justified"
move: one nobody asked for is put back, or the person is asked before the PR.

**Why.** Four corrections of the same kind in two days, the last two after the w826 check existed:

1. 2026-10-09 (w722/w723): "you did more with the overall layout than i wanted. like the station controls are not being
   put above objectives. that's not what i wanted. objectives are on their own layer and game Ui panels should just show
   over top of them".
2. 2026-10-10 (#1282, fixed by w813): "why is station info at the top left? i didnt tell you to move that".
3. 2026-10-10 (w894): "the Station Info hover panel, it seems like you keep moving it to the top on the deck. I don't want
   that. I want it to just be in its normal position over the abilities ... So just leave it. Don't put it in formation
   with the other panels. It's just a hover panel that shows above the abilities. Just leave it there on the desktop and
   the deck."
4. 2026-10-10 (w895): "I also noticed that the actual normal hover panel is up, you put it up in the fucking, you know,
   array of panels up on the top left. Don't do that, put it back over the minimap, stop moving panels around that I
   don't ask you to move around. It's driving me crazy." And to the harness: "Please update the harness to not fucking
   move panels around unless I tell you to."

Why w826's check let 3 and 4 through, measured from the PRs and the code:

- **The baseline was the PR's parent.** w772 (0068ccf9b, 2026-10-09, "Deck dock keeps the Station Info box and hover card
  up beside the inventory") stacked both in the dock's top-left cluster (`DockedInfo`) before the census existed. Every
  later before/after diff saw them already there. °Life°'s report asked for the information to stay up, not for it to move.
- **"not asked: justified" passed.** #1397 (w873, the station controls panel) ran the census in the dock and it printed
  Station Info and the hover card at y -119 px. The worker marked them "not asked: justified: the docked cluster stood under
  the strip ... with the strip gone it stands at the top", folded them into one line with the inventory, and
  `pr_evidence.py` 1.25.15 posted PASS with a note. w873's own brief said "Don't move any other UI that Ben didn't ask to
  move".
- **Quotes were not checked.** #1392 (w878) quoted "Station Grid Information on the left of center" and "Range panel and
  Defense Platform panel side by side, around the vertical center line": the first nobody said, the second is the
  dispatcher's description of a screenshot. `--brief` was optional and was not used.
- **Nothing required the docked layout or a selected station.** The `Moved:` line needed two sizes, not a layout. #1392
  reported "0 moves at 1280x800" without saying which layout. w815 (#1337) changed only the Steam Input layout file, so no census applied.

**How to apply.** [The UI checklist](../checklists/ui.md), the hard rule at its top and item 22: census 1920x1080,
1280x800 and 1280x800 docked with a station selected; `ui_layout.py moves` and `ui_layout.py pins`; every move asked in the
brief's own words; `pr_evidence.py --brief`. The places Ben fixed himself are in `unity-ui/hud-pins.json` with his words, and
`ui_layout.py pins` checks them in every census whatever the parent showed. MEASURED (editor censuses of develop 9798f308c,
`unity-ui/tests/fixtures/w894-develop-*.json`): it breaks Station Info (bottom edge at 264 of 800 px, centre x 282) and the
hover card (right edge at 358 of 1280 px) at 1280x800 docked, and passes 1920x1080 and 1280x800 undocked. The fix itself is
w895's.
