Request: w723
Request: w727

**TL;DR:** the classic layout on a Steam Deck gives every panel its own place: the Station strip fixed top-left, the objectives card under it, a two-column Station Info box beside them, and a building's windows, the station grid window and the player's inventory packed into the clear room around them (the Player Inventory keeps at least 3 rows and scrolls). The Deck's UI scale is 0.80, locked only in the structured layout; the classic layout has its slider back. Text is raised to a 9 px floor at 0.80.

## What changed

- **Layout (w723)**: `ClassicPacker` (new, pure) replaces the classic `SelectionColumnLayout.Arrange` search. Fixed HUD it never covers: the strip (w722's spot), the objectives card (measured from its `ObjectiveItem` cards after w722's `KeepObjectivesOff` moves it under the strip), the Station Info box. Then the hotbar and minimap corner, the hover card's tallest zone (soft). Cost order: covering fixed HUD or a window, soft HUD, height given up, distance from where the player left a window. A building's window shortens through `WindowFit`; the Player Inventory beside a building shrinks to `InventoryGridFit.MinRows` (3) and scrolls; the player's own Inventory and Crafting windows are moved, never cut (and kept off the objectives card when open alone). `ArrangeLeft` (w717's Command Core column) is on the same API. `SelectionColumn` caches the arrangement and re-runs it only when an input changes.
- **Station Info box**: `StationInfoLayout` regroups the scene's own rows into two columns with fixed label and value widths (measured from the widest realistic text in the current language) and fixed-pitch digits (`<mspace=0.6em>`); it sits beside the strip column, always in the same place in the classic layout.
- **UI scale (w727, and Ben's "if a steam deck user isnt using structured layout then they should be able to use UI scale again")**: `DeckUiScale` 0.80; only the structured layout locks it (`RangeFor(deck, structured)`); a Deck player who never moved the slider starts at 0.80 in classic (`UiScaleChosenKey`), their own value is kept aside in the hub and returns in classic. Reset UI Layout goes to the device default. Desktop stays 0.90.
- **Text floor (w727)**: `UiScaler.MinLegibleFontSize` 16 (9.3 px in Liberation Sans, 9.6 in Khyay at 0.80); the existing census tool raised about 480 prefab and scene texts; `TextLegibilityCensus` measures at the Deck's scale and raises a nested prefab's text where its placement needs it.
- Not mine, merged in: w722's strip spot and `reserved` API (#1280), w717's `ArrangeLeft`.

## Evidence

Kind: ui

| Claim | Basis | Where |
|---|---|---|
| No two panels overlap at 1280x800 at 0.80 and 0.90 and at 1920x1080 (building window, station grid window, inventory, strip, objectives card, info box) | MEASURED: `ClassicDeckLayoutTest` (pure layout, scenario sizes measured in a built player), 4 mains x 4 start places, with and without the grid window; also with the player's Inventory and Crafting open | Assets/Tests/UI/ClassicDeckLayoutTest.cs |
| At 1.0 nothing covers the strip, the objectives card or the info box | MEASURED: same test, including every window open at once | same |
| Player Inventory shows at least 3 rows, whole | MEASURED: test asserts the packed height; built-player stills at 0.80 and 0.90 | shots-final.md |
| Station Info keeps one size and place across buildings, scales, German and 1080p | MEASURED: value boxes at the same right edge and y in the census JSON of the Atomic Printer, Assembler and Mass Driver stills | shots-final.md |
| 0 texts under 9 px at 0.80, in both Deck fonts | MEASURED: Deck tour census at 1280x800: 0 under 9 px, smallest capital 9.0 px, every shot; `TextLegibilityTest` over every prefab and the main scene | /srv/fff/review/w723-classic-deck-ui/shots-final.md, specs/w644-deck-release/uiscale.md |
| Slider shows in classic on a Deck, hidden in the hub; 0.80 default; values kept per layout | MEASURED: `DeckUiScaleRangeTest` (8 tests), Settings logic read in `InterfaceOptions.RefreshUiScaleRow` | Assets/Tests/UI/DeckUiScaleRangeTest.cs |
| Fast suite green | MEASURED: batchmode FFEditorTests at the final commit, 8874 run, 8852 passed, 0 failed, 22 skipped | local run |
| The layout holds to about UI scale 1.0 and not at 1.2 | MEASURED: stills at 1.0 and 1.2; the hover card (w714's) covers a window edge at 1.0, and at 1.2 the top-left HUD takes a third of the width and a window is cut | shots-final.md |

Intended look (Ben): "every panel has its own place", "UI should be clean and flowy!", "player inventory and station grid panels" no longer "fucked"; "the game's existing panel colours and style" (the strip, objectives, info box and windows keep their sprites and colours; nothing new is drawn).
Built player: yes, development builds of this branch at 1d0a04580 and d56c5a709 (the final code; later commits are the census table, tour and tests), 1280x800 at 0.80, 0.90, 1.00, 1.20, German, and 1920x1080
Clips: /srv/fff/review/w723-classic-deck-ui/after-1280x800-ui0.8-atomic-printer-idle-realtime.mp4 (4 s at the player's own rate, 407 frames, about 101 fps, the whole screen idle); `ui_check.py flicker`: 0 flickering regions
Flicker: 0 regions in 407 frames (`scripts/deck_audit/ui_check.py flicker`, whole screen)
Looked: yes, at full size, every still in shots-final.md except the HUD-alone still, the German Atomic Printer still and the 1080p inventory still (looked at in the previous build with the same layout)
Content: a new game with the objectives card open, the inventory full (one of every building), an Atomic Printer, an Assembler and a Mass Driver placed (`specs/w723-classic-deck-ui/make_tour.py`); not a late-game save, since no late-game save with objectives open exists (the late-game save available has every objective finished)
Full content: the Station Grid window scrolls (scrollbar) and shows its power block; the Mass Driver window scrolls and keeps its buttons whole; the Player Inventory shows every slot row at 0.80 and 0.90; Inventory and Crafting windows show their whole grids (never cut)
Style: the classic windows' own sprites and colours are used unchanged (no new colours or sprites were added); the Station Info box keeps its frame and text colours; compared by eye in the stills against the before stills, same save
Shots: /srv/fff/review/w723-classic-deck-ui/shots-final.md (one line per still against Ben's words)
Review: no blind model review (no Gemini key here)

Tests: FFEditorTests 8874 run, 8852 passed, 0 failed (22 skipped as before); `ClassicDeckLayoutTest` 11 cases, `DeckUiScaleRangeTest` 8, `SelectionColumnLayoutTests` (w722's and w717's, on the new engine) all green
Save compatibility: none, no saved state is touched (a new PlayerPrefs key `UiScaleChosen` is local, never in a save)

Not verified: Deck hardware; a late-game save with the objectives open (none exists); the Station Info figures changing every heartbeat in a clip (the fixed widths are shown by constant right edges across stills); the hover card (w714's) still covers a window edge at 1.0 and above; 1.2 and higher in classic runs out of room (documented in uiscale.md); desktop text is 1 point bigger where it was 14 (the floor 14 to 16 for Liberation Sans, 15 for Khyay); w717's Command Core column in classic was not re-driven in a built player in this branch.

## Docs

`docs/UI-Architecture.md` (the classic packer, the UI scale, the info box), `specs/w644-deck-release/uiscale.md` (the 0.80 census and the decision), `specs/w723-classic-deck-ui/` (the tour).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

