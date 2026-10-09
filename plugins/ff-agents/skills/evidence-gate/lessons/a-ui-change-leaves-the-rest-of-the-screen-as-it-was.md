---
name: a-ui-change-leaves-the-rest-of-the-screen-as-it-was
description: "A UI change proves it left the rest of the screen as it was: a whole-screen layout census before and after (whole HUD showing, every slide-out open) with no new overlap between HUD blocks, no anchored cluster drifting more than 2 px, and every touched panel's measured colour and alpha within reach of a classic panel's; checked by the released pr_evidence.py, not an older copy."
date: 2026-10-09
---

# A UI change leaves the rest of the screen as it was

**Rule.** Checking the panel you changed is not enough. Before a UI change is done, take the layout
census (`unity-ui`, `layout-census.md`) before and after, same save and size, with the whole HUD
showing and every slide-out open, and run `ui_layout.py check`:

- no new overlap between HUD blocks, and none left between blocks you moved;
- no anchored cluster (the minimap and its side buttons, the hotbar, the top bar) drifting more than
  2 px against its anchor;
- every panel you touched, measured on screen against a classic panel: delta E 10 or less, the same
  art, the same see-through.

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

**Corrected, 2026-10-09 (w732).** Not every overlap is a defect. Ben's words were that the
slide-out panels "still intersect with the hotbar"; w732's brief turned that into "0 overlapping HUD
element rects", the worker moved the slide-outs above the toggles, and Ben corrected it: they open
where they used to and draw on top of the hotbar (the worker's words). A slide-out opened over the
hotbar, or the Inventory and Crafting windows that have always opened over it
(`specs/w644-deck-release/uiscale.md`), is design. `hud-clusters.json` now lists that pair under
`byDesign` with the person's words, and `ui_layout.py` prints it as BY DESIGN instead of failing it.
Add a pair there only from a person's own correction, never to make a check pass. Fix what your
change displaced (here #1264's `HudCornerSpacing`) before you move anything else.

**How to apply.** [The UI checklist](../checklists/ui.md), items 11 to 14, and the `unity-ui`
skill's `layout-census.md`:

- Census before and after with the whole HUD up and every slide-out open; `ui_layout.py check
  --touched <your window> --shot after.png --ref-shot <classic still>`.
- Paste its `Overlaps:`, `Alignment:` and `Style:` lines. `pr_evidence.py` fails a UI PR without
  them, with a new overlap, a drift over 2 px or a delta E over 10, unless the line quotes the
  requester asking for it: `intended (Ben): "..."`.
- Run it yourself before every UI merge and post its verdict (`--comment`); nothing in CI runs it
  yet (w733: a job is written, waiting for someone whose token may push workflow files).
- When a check changes mid-task, re-register (`registerAgents.sh`), restart, and run it again before
  merging. `pr_evidence.py` names its version in its verdict and fails when GitHub has a newer one.
