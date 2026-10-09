---
name: verify-ui-with-full-content-like-a-player
description: "A UI change is verified the way a player sees it: every screen and sub-view in a late-game save, in a built player at the target size, showing its whole content, on the classic panels' colours and art, still in a real-rate clip, each still checked against the requester's words. A tour that proves each tab opens and fits passes a broken screen. A Deck tour on a PC is a stand-in: a Deck-facing change is verified on a real Deck or reported 'not verified on a real Deck' (w770)."
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

- **It happened again with every check in place (w764, 2026-10-09).** MEASURED: the next Build, 90, had the full tour
  and the rules above, and a player (Discord, "New Steam Deck GUI notes") posted ten photos of a real Deck with eight
  faults none of them listed: the Technology tab's tile list two rows and a bit ("too small to actually be useful"), the
  Fleet header "Count" cut to "Coun" over "t", the Info tab empty after a load, the objectives card drawn over a Command
  Core's fields, windows laid over one another, the Mass Driver's "Intermediates" cut by a scroll bar. The census had no
  count for a cut word or a list's visible rows, and the tours never loaded a save with completed objectives, never kept
  the objectives card up while a Command Core opened, and never hovered a station with the inventory open. Each fault
  reproduced in the dev player the first time the state the photo shows was set up; none needed Deck hardware.

**How to apply.** [The UI checklist](../checklists/ui.md), and the `unity-ui` skill for the recipe:

- **A player's photos are tests (w764).** Put each photo beside your still of the same screen in the same state before the
  first fix; reproduce it in the built player (set up the state it shows); where the census stays quiet about what the photo
  shows, add the count to the census in the same change (since w764: `midWord` and `shortLists` in `DeckTourChecks`, with
  the failing case as a test fixture).

- Write the requester's words per screen first, with what "full content" means for each.
- Tour a late-game save; open every sub-view; `waitFor` content.
- For each still: `ui_check.py fill` for the pane, `ui_check.py style` against the classic panel
  from the same save, and one written line against the requester's words (`ui_check.py shots`).
- Record each screen at 30 fps or more and run `ui_check.py flicker`.
- In the PR, the `Content:`, `Full content:`, `Style:` and `Shots:` lines; `pr_evidence.py` fails a
  UI change without them (its fixture `pr-1251-deck-hub.md` is this PR, and fails).

## A simulated Deck is not a Deck (w770)
**The rule.** A change a Steam Deck player meets is not "done" on a Deck tour alone. The report
says "verified on a real Deck" with who, the Steam client and SteamOS versions, and what they saw,
or says "not verified on a real Deck" and what that leaves open. The checklist is
[deck.md](../checklists/deck.md); `pr_evidence.py` fails a Deck-facing PR with neither.

### Why: two corrections from Ben, 2026-10-09

- **w684 -> w768 (controller glyphs).** w684 closed done with PR #1249 on a Deck tour; its worker
  "could not confirm on real Deck hardware". On his Deck, Build 91, Ben: "Why aren't the Steam UI
  buttons, like the controller buttons showing anywhere?" The Deck ran Steam's Keyboard (WASD) and
  Mouse template, so Steam gave the game no action set, and every Deck button arrived as a real key
  that switched the prompts back to keys. w703 had also removed the fallback. His Deck's Steam
  client was out of date too: "omg my steam firmware was just way out of date lol. the controller
  layout shows after i updated". Fixed in PR #1300 (w768).
- **w767 (startup resolution).** Ben: "it's not taking up the whole width of the Steam Deck
  screen... It just looks like it's not rendering properly, like the aspect ratio is all messed
  up." The game stored the first-frame screen size (portrait 800x1280 under Proton) and re-applied
  it on every launch. The Deck tour forces its own windowed size every second and starts from clean
  prefs, so it could never see it. Fixed in PR #1301 (w767).

Both were the second correction of one kind on the same day: a fix verified on a stand-in for the
Deck, whose blind spots nobody named. A tour that passes tells you the stand-in works.

### How to apply

1. Before you write "fixed" on a Deck-facing change, list the four things a simulated Deck cannot
   show (template vs official layout, first-frame resolution under Proton/gamescope, Steam client
   and SteamOS version, touch) and say which your change touches.
2. Run the cheap stand-ins ([deck.md](../checklists/deck.md)), then ask for the real Deck through
   your orchestrator with the steps written out, starting with "the Deck's Steam client and
   SteamOS are up to date" (the w768 worker's proposal, adopted).
3. If nobody can look yet, write "not verified on a real Deck" in the report and the PR's
   `Real Deck:` line, and keep the request open when it is a player's report from their own Deck (`wNNN: still open: waiting on <name> to check on the Deck`).

### What was built and what was left (w770)

| Check | Status | Why |
|---|---|---|
| `Real Deck:` line on a Deck-facing PR | **Built**: `pr_evidence.py` `deck_problems`, fixtures of both cases | Needs only the PR text and its file list, which this repo already reads. |
| Checklist and ask template | **Built**: [deck.md](../checklists/deck.md), linked from the done, merge and UI lists | What a person must look at cannot be a script. |
| Keyboard-template simulation | **Already in the game repo** (w768, PR #1300: `-ffDeckTourFallback`, the `key` step, `specs/w768-deck-template-glyphs/template-tour.json`) | Nothing to add here; the checklist points at it. |
| Deck tour that does not force the size and starts from stored prefs | **Built in the game repo (w771, PR #1304)**: `-ffDeckTourSize none`, `-ffDeckTourPrefs <json>` | Measured on a Mac dev player: 800x1280 stays stuck before #1301, repaired to full screen on develop. The first-frame portrait read stays Deck-only. |
| Touch, Steam client version, whether the official layout is offered | **Checklist line only** | They exist only on the device. |

**The proposal for the game repo, as made (w771; the first-frame step was not built):**
`-ffDeckTourSize none` (or `-ffDeckTourNoResize`) skips the forced `Screen.SetResolution` in `Update`
and `HoldSize`; `-ffDeckTourPrefs <json>` writes `ResolutionWidth`, `ResolutionHeight` and
`FullscreenMode` (and a `DarkModeSkybox`-less first launch) before `PlayerSettingsController.Start`;
a tour step reads `Screen.width/height` at frame 1 and again after `StartupRecheckFrames`, and fails
when the window is not landscape or does not fill the display. The first-frame portrait read is
reported only under Proton (`Documentation/Display-Startup.md`), so a PC tour would test the repair,
not reproduce the Deck's first frame.
