**TL;DR:** on a desktop, a building's windows now open as one cluster around the middle of the screen (Ben's Defense Platform and Ship Assembler arrangements) instead of wherever the scene draws each one. Only the first-open defaults: windows the player dragged stay put. Small screens (the Deck) and the Command Core column are untouched.

Request: w878

Ben, w878: "on desktop i dont love how the panels dont really cluster in the middle by default ... i want these to be the defaults. use the center of the screen!" and "wow i hate select recipe being all the way over to the left, again just use the middle of the screen like in the after shot".

## What changes

- `UI/Components/DefaultPanelCluster.cs` (new, pure geometry): the main window starts 40 units left of the room's vertical centre; the side windows (station grid information, defense platform range, recipe picker, logistics) stand level with its top, the first on its left, the next on its right, then left again; the inventory is centred under the main window (beside it when the two together are taller than the room above the hotbar); the cluster's middle sits at 0.56 of the room's height, lifted above the hotbar and the minimap corner and moved right of the Station strip.
- `SelectionColumn.DefaultCluster` sets those places as the *wanted* places that `ClassicPacker` already searches from, so the packer still has the last word (nothing over the strip, hotbar, minimap or another window). Windows with a remembered or dragged position (`Header.PlacedByPlayer`) are not touched; a placed main window is where the others hang from.
- Skipped on a small screen (`SmallScreen()`, the Deck: w644/w815) and for a Command Core (`ArrangeLeft`, w717). The station controls panel (w873) is not touched.
- `docs/UI-Architecture.md` records the rule; `specs/w878-cluster-defaults/` holds the tour, the clip leg and the census check used below.

## Evidence

Kind: ui

| Claim | Basis | Where |
|---|---|---|
| A Defense Platform opens as Range (left), main (right), inventory centred under the main window | MEASURED: built player, census rects at 1920x1080 and 2560x1440 | review/w878-panel-cluster/after-*-defense-platform.png, census-check.txt |
| An Assembler, Atomic Printer, Ship Assembler open with the station grid on the left of centre and Select Recipe on the right, tops level | MEASURED: built player, same | review/w878-panel-cluster/after-*-assembler.png etc. |
| No window overlaps another or covers the HUD (hotbar, minimap, quick buttons, top bar, strip, station info, hover card) | MEASURED: `check_layout.py` over the layout census of all 5 buildings at both sizes: 0 problems | review/w878-panel-cluster/census-check.txt |
| A dragged window stays where it was put and is kept after reopening | MEASURED: drag Station Grid Information, close, reselect, built player | review/w878-panel-cluster/persist-*.png |
| The windows do not flicker | MEASURED: `ui_check.py flicker` over the whole frame of a 3.5 s real-rate clip per building, 0 regions | review/w878-panel-cluster/*.mp4 |
| The cluster is centred and non-overlapping on every desktop screen | MEASURED: `DefaultPanelClusterTests` over 1920x1080, 2560x1440, 3440x1440, 1920x1200 at UI 0.9 and 1.0, five buildings with the measured window sizes | Assets/Tests/UI/DefaultPanelClusterTests.cs |
| Nothing else on the layout moved | MEASURED: `ui_layout.py check` before/after, 0 new overlaps, alignment max drift 0 px | below |

Intended look (Ben): "the Range panel and the Defense Platform panel side by side, around the vertical center line"; "Station Grid Information on the left of center, Select Recipe on the right of center, their tops roughly level, the pair centred on the screen a bit below the middle"; "use the center of the screen!" (his screenshots, described by his orchestrator; the production-building one is a Ship Assembler).
Built player: yes (macOS Development players of 07783be9c and 636231b4a, the slot pool, a fresh PlayerPrefs domain so no remembered positions)
Clips: review/w878-panel-cluster/before-1920-defense-platform.mp4, after-1920-defense-platform.mp4, before-1920-assembler.mp4, after-1920-assembler.mp4 (about 50 fps; the opening is in frames 0 to 10, then the windows hold still; before and after open the same way)
Looked: yes, every after still at full size, and the opening frames of the Defense Platform and Assembler clips on a contact sheet
Review: no blind model review run
Content: a new game (HandHoldy), the five buildings put down with `blueprint.place`; the player's inventory is the early-game 6-row one. A late-game 100-slot inventory (590 units tall) is covered by the unit test's measured sizes, not by a built-player still.
Full content: yes, every window shows its whole content in the stills: Select Recipe with its tabs and recipe, Station Grid Information with Power/Heat/Signal and the three tables, Range with both sliders, the Player Inventory with every row.
Style: GamePanels/DefensePlatformEntityPanel/MainPanel (touched) vs UI Canvas/GamePanels/MiniInventory: delta E 4.3 (on screen), alpha 1.00 vs 1.00, same art; GamePanels/LogisticsNetworkEntityPanel/MainPanel (touched) vs UI Canvas/GamePanels/MiniInventory: delta E 4.8 (on screen), alpha 1.00 vs 1.00, same art (`ui_layout.py check --ref MiniInventory`, the before still as the reference; no colour, art or alpha was changed, only positions)
Shots: after-1920/2560 defense-platform (Range left, main right, inventory centred under main), assembler / atomic-printer / ship-assembler (grid left, Select Recipe right, tops level), mass-driver (a tall window: the inventory stands beside it, left; nothing over the HUD)
Flicker: 0 flickering regions over the whole frame (`ui_check.py flicker`, five buildings, 204 to 221 frames each)
Overlaps: 0 block pairs before, 0 after, 0 new, 0 kept (`ui_layout.py check`, Defense Platform and Assembler, 1920x1080)
Opened panels: the Station strip over the objectives card as before this change (w813); the building's windows over no HUD, 0 not clickable, 0 cut off
Alignment: max drift 0 px over the clusters (bottom-right HUD, top-left HUD), tolerance 2 px
Moved: 5 element move(s) over 4 px at 1920x1080, 1280x800 (ui_layout.py moves, the same new game and screens before and after; 0 moves at 1280x800 at UI 0.8: the Deck layout is untouched, 2560x1440 is in the stills); mark each below: asked (who): "their words", or not asked: justified: <why>
- 1920x1080 GamePanels/MiniInventory: x +590, y -188 px (was 298,662 491x293, now 887,474 491x293): mark: asked (Ben): "use the center of the screen!"
- 1920x1080 GamePanels/LogisticsNetworkEntityPanel (the Defense Platform's own window): x +553, y -64 px (was 371,250 418x281, now 924,186 418x281): mark: asked (Ben): "use the center of the screen!"
- 1920x1080 GamePanels/DefensePlatformEntityPanel (its Range window): x -320, y -113 px (was 796,353 437x215, now 476,240 437x215): mark: asked (Ben): "Range panel and Defense Platform panel side by side, around the vertical center line"
- 1920x1080 GamePanels/StationGridEntityPanel: x -657, y +0 px (was 1035,186 700x581, now 378,186 700x581): mark: asked (Ben): "Station Grid Information on the left of center"
- 1920x1080 GamePanels/AssemblerEntityPanel (Select Recipe): x +492, y +31 px (was 432,307 393x374, now 924,338 393x374): mark: asked (Ben): "just use the middle of the screen like in the after shot"

Tests: Tests.UI DefaultPanelClusterTests (6), SelectionColumnLayoutTests, SelectionColumnPanelsTests, PanelLayoutTest, PlayerPlacedWindowTests, ClassicDeckLayoutTest, HeaderRestoreTest, PlayerWindowsHoverTests, ResetUiLayoutTest, PanelRolesTest, CommandCoreObjectivesTests: 120 run, 120 passed (the selection the change touches; CI runs the whole suite)
Save compatibility: none, no saved state is touched (PlayerPrefs positions keep their format)

Real Deck: not verified on a real Deck: nothing about the Deck changes (1280x800 at 0.8 shows 0 moved windows before/after in the tour), so no Deck hardware was reached.

Not verified: a 1920x1080 screen with a late-game inventory in a built player; three side windows open at once on a 1080p screen (the row is wider than the room: the packer places them, the unit test only holds them off the HUD and the strip); Windows and Linux players (a Mac player only); a real multi-monitor or ultra-wide.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
