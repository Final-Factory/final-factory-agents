---
name: verify-ui-with-full-content-like-a-player
description: "A UI change is verified the way a player sees it: every screen and sub-view in a late-game save, in a built player at the target size, showing its whole content, on the classic panels' colours and art, still in a real-rate clip, each still checked against the requester's words. A tour that proves each tab opens and fits passes a broken screen."
date: 2026-10-08
---

# Verify UI with full content, like a player

**Rule.** A screen is verified when a still of it, taken in a late-game save in a built player at
the target size, shows its whole content (every row of the grid, the tree, the preview), looks like
the classic panel it replaces, holds still in a real-rate clip, and has been described line by line
against what the requester asked for. "Opens", "fits" and "no text under 9 px" are necessary and
far from enough.

**Why.** The w644 hub (#1251, merged 2026-10-08, shipped in Build 89) passed a scripted Deck tour:
14 stills at 1280x800 and 14 at 1920x1080, 0 failures, "Looked: yes, every shot at full size". On
Ben's real Deck nearly every tab was broken: dark navy where the game's panels are teal-blue,
Crafting cut to one row, Technology with no tech grid, the Blueprints preview off the bottom with
flickering icons, Factory info using a fraction of its pane. Why the tour missed it (w718):

- **It checked the wrong claims.** MEASURED (#1251's Evidence): every row is "opens", "switches",
  "B closes", "fits above the hotbar", "no text under 9 px". No row says a tab shows its full
  content or matches the classic look.
- **The colour was typed into code and never compared.** MEASURED: `StructuredHub.Shade` fills
  the hub with `new Color(0.04f, 0.07f, 0.11f, 0.96f)` (`StructuredHub.cs:527`), #0a121c, nearly
  opaque. The classic Inventory panel, translucent over space, samples at #163a56 (its most common
  colour in a w524 still at 1920x1080): delta E 22.4 by `ui_check.py style`.
  The only classic check was "129 texts both times", a count.
- **The "before" had nothing to compare.** MEASURED: the before arm was develop, where the keys
  opened nothing new ("before-1280-b2-R1-no-tab.png: nothing open"), so no still showed the classic
  screen beside the hub.
- **Thin content, and sub-views never opened.** MEASURED: the PR says "The Info tab is the
  objectives list; the test save has none, so it shows only its header", and `tour/hub.json` only
  presses R1 and shoots: no blueprint is selected, so the preview that ran off Ben's screen never
  appeared. GUESS: a late-game save's longer recipe and tech lists are what cut Crafting to a row
  and emptied Technology on the Deck; w716 owns the cause.
- **Known cuts went to "Not verified" while the title said it works.** MEASURED: "WindowFit cut
  Crafting's list far more than needed when the pane was 17 px short ... the cut itself is
  unchanged", and Factory info's box "keeps a fixed height, so it gets the docked fit", against
  Ben's words for the hub: "the ui content should just fit in the whole pane of the hub panel".
- **The clips could not show flicker.** MEASURED: "Clips: ... 1 fps sequences of the tours'
  shots", with "Review: no watch_video: layout changes, no animation". The Deck tour has a `record`
  step that saves every frame (`DeckTour.cs`, `Record`); the hub's tour never used it. The hub's
  own code notes that two fits fighting over one list "made the window jump".
- **Fixed waits.** MEASURED: each shot follows a `wait` of 1.5 to 2.5 s, not a `waitFor` on the
  content. GUESS whether any still was taken before its screen had filled.
- **The census only reads text.** MEASURED: the tour's census counts texts under 9 px, clipped,
  off screen, overlapping, and covered controls. It has no measure of a grid's visible rows, a
  window's share of its pane, a background colour, or motion. Its "12 clipped blueprint names" were
  waved through as "the tiles' own ellipses".
- **It had happened before.** SOURCED: Ben's rule of 2026-09-22 (project-memory
  `ui-screenshot-worst-case-before-done`) already said "Render the WORST case, not the demo case".
  It lived in a memory nobody's checks read. This time the rule is in `pr_evidence.py`, which
  fails a UI pull request that does not name its content, style, stills and clip.
- **No Deck hardware.** MEASURED: listed under "Not verified". GUESS how much of the miss is the
  real Deck (Proton, real Steam Input, a multiplayer client) rather than content.

**How to apply.** [The UI checklist](../checklists/ui.md), and the `unity-ui` skill for the recipe:

- Write the requester's words per screen first, with what "full content" means for each.
- Tour a late-game save; open every sub-view; `waitFor` content.
- For each still: `ui_check.py fill` for the pane, `ui_check.py style` against the classic panel
  from the same save, and one written line against the requester's words (`ui_check.py shots`).
- Record each screen at 30 fps or more and run `ui_check.py flicker`.
- In the PR, the `Content:`, `Full content:`, `Style:` and `Shots:` lines; `pr_evidence.py` fails a
  UI change without them (its fixture `pr-1251-deck-hub.md` is this PR, and fails).
