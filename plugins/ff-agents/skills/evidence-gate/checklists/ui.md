# UI changes: verified the way a player sees them

For any change to a panel, window, tab, HUD element, menu, popup or layout (docking, tabs, scaling,
the structured layout, Steam Deck sizing). The [visual checklist](visual.md) applies too; this list
adds what a screen needs. The recipe (the Deck tour, the pixel checks, uGUI pitfalls) is the
`unity-ui` skill.

**The line that would have caught w644's hub** (#1251, Ben's Deck, Build 89):
every screen and sub-view, in a late-game save, at the target size and UI scale in a built player,
shows its whole content (grid, list, tree, preview) on the classic panels' colours and art, holds
still in a real-rate clip, and each still is described against the requester's words before
anyone says done.

1. **The requester's words, per screen.** Before the first shot, write one line per screen: what
   the person said it must show or do (quote them), and what "full content" means for it
   ("Crafting: every row of the selected category's recipe grid", "Technology: the tech tree grid
   with its nodes", "Blueprints: the list, and a selected blueprint's preview whole on screen",
   "Factory info: its stats filling the pane"). This list is what each still is checked against.
   **Only the person's words are targets.** A brief's reading of them ("top and bottom edges
   aligned with the minimap frame") is a guess until the person says it; build only what the words
   say, and where the person says "like before" or "as it was", the target is the *before* still:
   measure it (gap, pitch, edge offsets) and pin those numbers in the test, so the fix restores them
   and invents no new alignment. w732: Ben said "hugging the minimap nicely (with a little padding)";
   the brief said "top and bottom edges aligned", the fix stretched both button columns over the frame's
   height (toggle gaps 5 -> 32 units), and Ben: "I don't want the minimal icons to fill the vertical
   space. I want them to stack with a little padding like before."
2. **Realistic, full content.** A late-game world: many recipes and techs unlocked, a tech tree
   partly researched, 10 or more blueprints, a fleet, objectives in progress, a full inventory,
   long names. A new game, a test save with empty tabs, or a dev-built world of one-off buildings
   is not enough: it cannot show a grid that overflows or a list that is too long. Name the save in
   the PR (`Content:`). Where a tab is empty in that save, it is "not verified", not PASS.
3. **Every sub-view a player reaches.** Each tab, and inside it the selected item, hover card,
   preview, popup, the second page, the list scrolled to its end. A tour that only switches tabs
   tests the tab strip.
4. **Wait for the content, not for a time.** Shoot after a `waitFor` on something that appears only
   once the screen is filled (a tree node, a recipe in the last row, the preview image), not after
   a fixed `wait` of a second or two.
5. **Full content, per still.** The panel shows its whole grid, list or tree, or scrolls to it.
   Nothing cut off, off screen or under another panel; no grid reduced to one row; no tab whose
   content uses a corner of its pane (`ui_check.py fill` reads under 60 %). A census flag
   ("clipped", "off screen") is a finding until you have looked and written why it is not one.
6. **Style parity with the classic panel.** Put the new screen and the classic one side by side,
   same save, same size. Colours (`ui_check.py style`: background delta E 10 or more flags it),
   frame art, fonts, icon sizes; item 13 measures it per touched panel. Reuse the classic skin; a colour typed into code is a finding
   unless the requester asked for it, quoted; an approved mock is not an approved skin (#1251 built
   the hub from the round-3 mocks; Ben: "you made the inventory panel hub thing dark blue, why did you
   change that? it should show the right colors"). "Before" is the classic screen with the same content,
   not develop with nothing open.
7. **No flicker: a real-rate clip.** Each screen idle for 3 s or more, and while hovering,
   selecting and scrolling, recorded at 30 fps or more (the Deck tour's `record` step, or
   `record_clip`). `ui_check.py flicker` reports 0 regions. A 1 fps slideshow of the stills is not
   a clip, and "layout change, no animation" is not a reason to skip it: a layout that fights
   itself flickers.
8. **The target, as the player has it.** A built player, the target resolution and UI scale
   (Deck: 1280x800 at 0.80, its default since w727, and 0.90, in both layouts; desktop: 1920x1080
   at the default 0.90), the player's input (the
   Deck tour's scripted Deck), both layouts where both exist, as a multiplayer client too where the
   screen differs there. A real Deck when one can be reached; otherwise "Not verified: Deck
   hardware".
9. **One line per still, written while looking.** What it shows, whether the content is whole,
   whether it matches the classic look, which of the requester's words it meets or breaks
   (`ui_check.py shots` writes the sheet). That sheet is "Looked: yes". A contact sheet is for
   finding problems, never for passing them.
10. **Show the person.** When the person asked for the look, the PR and the report put the stills
    of every screen in front of them (`publish_review`), so they see the hub before a player does.

**The rest of the screen** (w733: the minimap's side buttons drifted off it and a slide-out covered
the hotbar, while each PR checked its own panel; #1272 turned the Blueprints window opaque navy).
The census recipe and `ui_layout.py` are in the `unity-ui` skill, `layout-census.md`.

11. **No new overlap between always-on HUD, and opened panels done properly.** A layout census
    before and after, same save and size, with the whole HUD showing (hotbar and ability row,
    minimap and its side buttons, every slide-out opened, top bar, objectives, a selected building
    and the Station strip) and your screen open on top. `ui_layout.py check` lists overlapping
    always-on HUD blocks; a pair that was not there before fails, and so does one left between
    blocks your change moved (`0 new, 0 kept`). **A panel the player opens on purpose and can close
    may cover the HUD** (Ben, w732: "Put the slide out back just make it appear over the hot bar.
    The user can then close it to show the hotbar again"; w742: "the blueprint panel showing over
    objectives is fine since its a temporarily opened panel"): Blueprints, Inventory, the slide-out
    flyouts, the Station panel, the hub. It is not an overlap failure, but the `Opened panels:` line
    must show it on top (0 under the HUD), clickable (0 not clickable: nothing under it catches the
    clicks), inside the screen (0 cut off) and the HUD back after closing (`--closed`, "HUD restored
    on close: yes"). What still fails: overlaps between always-on HUD blocks (hotbar and minimap
    buttons, ability row and hotbar, Objectives and minimap), a panel drawn under the HUD or cut off
    by the screen edge, drift (item 12) and colour (item 13). What counts as opened is
    `hud-clusters.json` `openedPanels`: add a window only when the player opens and closes it, never
    to make a check pass. Restore what your change displaced rather than moving other blocks.
    Re-take the census on the merged result when another UI PR landed in between (#1280 checked
    its merges by compile and tests only).
12. **No drift.** Every anchored cluster (`hud-clusters.json`: the minimap with the quick buttons,
    the slide-out toggles and the hotbar; the top bar with the objectives) keeps its edges and gaps
    against its anchor within 2 px. Changing a cluster on purpose: say so, and update the file.
13. **Every touched panel looks like the game's.** `--touched <window>` checks each panel you
    changed, and every panel the census sees change, against a classic reference panel
    (`--ref`, the Inventory by default) on screen (`--shot`/`--ref-shot`): delta E 10 or less, the
    same art, the same see-through. A sentence ("keeps its translucent look") is not a check.
14. **The released checks.** A session loads its plugins when it starts. Before you merge, run the
    released `pr_evidence.py`; its verdict names its version and fails when GitHub has a newer
    one. Re-register and restart when it does. Post its verdict on the PR (`--comment`) before
    you merge: no CI job runs it yet.

**The line that would have caught both w733 misses:** a whole-screen layout census before and after,
with the whole HUD showing and every slide-out open, shows no new overlap between HUD blocks, no
anchored cluster moved more than 2 px, and every touched panel within delta E 10 and the same
see-through as a classic panel, checked by the released `pr_evidence.py`.

**A change made for the Deck reaches the desktop too** (w761: #1282, "classic Deck layout", raised about 300 texts
from 14 to 15/16 pt on every screen and made the classic packer place the I-key Inventory and Crafting windows on every
screen; on desktop three labels stopped fitting, the two windows left their default spots, swapped sides at
2560x1440 and jumped when the mouse crossed a building; Ben's rule: the desktop default does not change unless asked).

15. **Desktop before and after, even for a Deck change.** 1920x1080 and 2560x1440, the desktop's default UI scale,
    the classic layout: the I-key Inventory and Crafting, a building with its windows, the Blueprints, Technology
    and Mods windows. Each window's rect matches the base commit's unless the requester asked for the move (quote
    them). With a window open, move the pointer over two buildings so the hover card shows (it reserves room, and a
    packer that keeps off it moves windows while they are open), and drag one window and reopen the others.
16. **A font-size change: every text compared.** Census before and after on every screen you can reach, then
    `text_diff.py` (unity-ui `layout-census.md`); look at each flagged text at full size. A label's fit is checked in
    the font it shows at runtime (`LocalizationHelper.ApplyFont`: Khyay for every Latin locale), not the font its
    prefab names.

17. **A player's photos, state for state (w764).** When the report is photos of a real device, each one is laid beside
    your still of the same screen in the same state before the first fix, and the state is set up in the built player
    (the objectives card up while a Command Core opens, Info after a real save and load, the pointer over a station with
    the inventory open, a long research queue, the Custom screen scrolled). A problem the photo shows that the tour's census
    does not count ("Count" cut to "Coun" / "t", a tile list showing 2.4 rows, a window under another) gets its count in
    the same change (`DeckTourChecks`: `midWord`, `shortLists`; the failing case is the test fixture). `ui_check.py shots`
    lists both beside `clipped`; each one is a finding until you have looked.
18. **Hidden means gone, and stays gone.** A fade or hide is checked 3 s after it was applied, not 0.3 s (the objectives
    card's own fade-in brought it back over a Command Core's column in half a second), and what is hidden takes no room
    (a faded card still held 330 units, so the window sat under nothing and was cut to three rows). A window the player
    placed is HUD to the windows the layout places: they keep off it.

20. **Every state the player can toggle, after a re-open, in the structured layout (w792).** A panel's toggles and tabs are
    switched on and off in the built player in each layout, and the docked pass closes and re-selects the building first: the
    dock changes a window's layout components when it docks (fitters off), and a row first laid out before the dock looks right
    while one docked first does not. Ben's Build 92 photo: the Ship Yard's Max buttons over the Requested field after exactly
    that order, which every earlier still (opened with the toggle already on) missed. The tour's `rowOverlaps` is 0 in every
    state.

21. **Layers are sibling order, and the test starts the object where the game creates it (w813).** In `GamePanels` a later
    sibling draws over an earlier one; a frame or panel built at run time is a last sibling, so it covers every window
    until something moves it. A test of that move starts the object last (the first w813 `PlaceAbove` test started the
    frame first, passed, and shipped a dock frame that hid and blocked every docked window; an adversarial review found
    it). Ben, w813: "objectives are on their own layer and game Ui panels should just show over top of them", so a
    window never keeps off the objectives card and the strip over it is the intended overlap (`openedPanels` lists
    `SelectionColumnStrip`).

22. **Nothing moves that the brief did not ask to move (w826).** Take the census before and after at both standard sizes,
    1920x1080 at UI 0.9 and 1280x800 at UI 0.8, the same save and screens, and run `ui_layout.py moves --pair
    before-1920.json after-1920.json --pair before-1280.json after-1280.json` (unity-ui `layout-census.md`). It lists
    every HUD block and window that moved or resized more than 4 px, with what moved inside it. Paste its `Moved:` line
    and list into the PR and mark each line:
    - `asked (Ben): "his words"` only when the words ask for **that element to move on that screen**. A Deck request does
      not move the desktop (`pr_evidence.py` fails a Deck quote on a 1920x1080 line). Words that ask for "a new place" ask
      for a move, not for the place you picked: name the place in the TL;DR and the report's first lines.
    - otherwise put it back and re-take the census, or mark it `not asked: justified: <why>` (a size the requester's
      change forces, such as a text floor they asked for) and name it in the report's first lines.

    Run `pr_evidence.py --brief <the brief, saved from read_work>` so every quote is checked against the requester's words.
    Ben, after w722/w723 had moved the objectives card under the Station strip: "you did more with the overall layout than
    i wanted. like the station controls are not being put above objectives. that's not what i wanted"; after #1282 had
    moved the Station Info box from above the ability row to the top left on every screen: "why is station info at the
    top left? i didnt tell you to move that". MEASURED (w826, editor censuses of 4762a5bc3 and 102e46bed): the check lists
    `GamePanels/BuildInfoPanel` at x -312, y -736 px at 1920x1080 and x -30, y -476 px at 1280x800.

22. **A layout change lists every HUD element it moved (w813).** Measure the base build (the commit before the first PR
    of the layout work) and yours with the same tour, and put a table in the PR: each element whose place differs, with the
    person's quote or "not asked". w722 / w723 moved the Station Info box to the top-left corner as a side effect of
    packing windows around the strip; nobody asked, and it shipped until Ben, 2026-10-10: "why is station info at the top
    left? i didnt tell you to move that". The evidence for a moved element is a still of it before and after, not the
    tests of the layout around it.
23. **A tour that switches layouts is not a classic still (w813).** In the built player the structured dock stays open
    when the tour switches back to classic with a building selected, so a "classic" still shot after a docked pass was the
    dock (the census names it: `StructuredDock`, `StructuredStation`). Run one layout per player launch, and read the census
    names of the first still before trusting a set of them.

19. **The Deck tour is a stand-in (w770).** It forces its own window size and a scripted Deck, so it cannot show Steam's
    layout choice, the Proton first-frame resolution, the Steam client version or touch. A Deck UI change says "verified on
    a real Deck" or "not verified on a real Deck" ([deck.md](deck.md)). For a stored bad size use `-ffDeckTourSize none
    -ffDeckTourPrefs` (w771): more coverage, still not a Deck.

In the pull request (`## Evidence`, [merge.md](merge.md)) a UI change adds:

```markdown
Content: late-game audit save w718-lategame.zip (212 techs, 140 recipes, 24 blueprints, 9 fleets, 6 objectives)
Full content: every tab's grid/list/tree whole or scrolling, fill 78-96 % (ui_check fill); Info lists 6 objectives
Style: BlueprintPanelChild (touched) vs InvAndCraft/InventoryPanel: delta E 2.1 (on screen), alpha 1.00 vs 1.00, same art
Overlaps: 4 block pairs before, 4 after, 0 new, 0 kept between blocks the change moved (ui_layout.py, whole screen, block depth 2); 1 opened-panel pair(s) over the HUD, not counted here
Opened panels: 1 opened panel pair(s) over the HUD (allowed: Ben, w732 and w742), 0 under the HUD, 0 not clickable, 0 cut off by the screen edge, HUD restored on close: yes (3 covered HUD element(s) checked in closed.json)
Alignment: max drift 0 px over the clusters (bottom-right HUD, top-left HUD); tolerance 2 px
Moved: 1 element move(s) over 4 px at 1920x1080, 1280x800 (ui_layout.py moves, the same save and screens before and after); ...
- 1280x800 GamePanels/BlueprintPanelChild: x +0, y +40 px (was 392,68 458x376, now 392,108 458x376): asked (Ben): "move the blueprint window down so it clears the top bar on the deck"
Shots: /srv/fff/review/wNNN/shots.md (one line per still against Ben's words)
Clips: after-1280.mp4, 60 fps; idle and hover per tab at 0-4 s, 4-8 s ...; ui_check flicker: 0 regions
```

`pr_evidence.py` fails a UI change without these lines, with a clip of 1 to 9 fps, with a new
overlap, an opened panel under the HUD, not clickable, cut off or leaving the HUD unrestored (the
`Opened panels:` line, required when the `Overlaps:` line counts an opened-panel pair), a drift over 2 px, a `Style:` line without a measured delta E and alpha, or a delta E over
10, a `Moved:` line missing either standard size or with a move not marked asked or justified (item 22). A difference the requester asked for passes with their words on its line:
`intended (Ben): "..."`. A scene file (`Assets/Scenes/*.unity`) counts as UI.

Lessons behind this list:
[verify UI with full content, like a player](../lessons/verify-ui-with-full-content-like-a-player.md),
[a UI change leaves the rest of the screen as it was](../lessons/a-ui-change-leaves-the-rest-of-the-screen-as-it-was.md).
