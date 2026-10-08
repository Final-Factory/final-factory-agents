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
   frame art, fonts, icon sizes. Reuse the classic skin; a colour typed into code is a finding
   unless the requester asked for it, quoted. "Before" is the classic screen with the same content,
   not develop with nothing open.
7. **No flicker: a real-rate clip.** Each screen idle for 3 s or more, and while hovering,
   selecting and scrolling, recorded at 30 fps or more (the Deck tour's `record` step, or
   `record_clip`). `ui_check.py flicker` reports 0 regions. A 1 fps slideshow of the stills is not
   a clip, and "layout change, no animation" is not a reason to skip it: a layout that fights
   itself flickers.
8. **The target, as the player has it.** A built player, the target resolution and UI scale
   (Deck: 1280x800 at its locked 0.90; desktop: 1920x1080 at the default), the player's input (the
   Deck tour's scripted Deck), both layouts where both exist, as a multiplayer client too where the
   screen differs there. A real Deck when one can be reached; otherwise "Not verified: Deck
   hardware".
9. **One line per still, written while looking.** What it shows, whether the content is whole,
   whether it matches the classic look, which of the requester's words it meets or breaks
   (`ui_check.py shots` writes the sheet). That sheet is "Looked: yes". A contact sheet is for
   finding problems, never for passing them.
10. **Show the person.** When the person asked for the look, the PR and the report put the stills
    of every screen in front of them (`publish_review`), so they see the hub before a player does.

In the pull request (`## Evidence`, [merge.md](merge.md)) a UI change adds:

```markdown
Content: late-game audit save w718-lategame.zip (212 techs, 140 recipes, 24 blueprints, 9 fleets, 6 objectives)
Full content: every tab's grid/list/tree whole or scrolling, fill 78-96 % (ui_check fill); Info lists 6 objectives
Style: against the classic Inventory and Crafting, same save, 1280x800: background delta E 2.1 (ui_check style)
Shots: /srv/fff/review/wNNN/shots.md (one line per still against Ben's words)
Clips: after-1280.mp4, 60 fps; idle and hover per tab at 0-4 s, 4-8 s ...; ui_check flicker: 0 regions
```

`pr_evidence.py` fails a UI change without these lines, or with a clip of 1 to 9 fps.

Lesson behind this list:
[verify UI with full content, like a player](../lessons/verify-ui-with-full-content-like-a-player.md).
