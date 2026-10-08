**TL;DR:** Stage A3 of w644 (the Steam Deck release UI), the w560 spec's hub (FR-015..FR-018). In the structured layout (the Deck's default; on desktop, the off-by-default "Structured layout (experimental)" setting), Inventory, Technology, Blueprints, Factory info, Fleet, Map and Info open as tabs of one full-screen hub. A tab strip runs across the top: L1/R1 or [ ] step the tabs, B or Esc closes, and each tab is also clickable. The screen's own windows sit frameless on one dark panel. Another screen's key switches tabs in one step; on develop it only closed the open screen. The tour also found that on the Deck the B that closes a structured panel boarded the nearest vehicle as well; that's fixed in Steam Input for the hub and the docked building panel alike. The classic layout is unchanged. Presentation and input only.

Part of: w644 (Steam Deck release UI).

## What changes

- `UI/Structured/StructuredHub.cs` (new, added by `UiController.Awake`):
  - Each frame it reads which of the seven screens is open (`UiController.ResolveAutomationPanelRoot`) and shows the hub over it. The strip is a `StructuredTabStrip`, with Deck glyphs from `ControllerPrompts`: L1 and R1 on the end tabs, B on Close.
  - **One-step switching:** another screen's key, with one open, makes that screen the only one open.
  - **Layout:** the screen's windows are docked frameless (`StructuredDock.DockedWindow`), side by side and centred. Technology, already full-screen, moves down under the strip.
  - **Single-window tabs (Fleet, Blueprints):** the main list fills the pane. `ListGrow` sets its height only when every box between it and the window takes the height its content asks for, and never grows it past the pane. The Factory info panel's statistics box keeps a fixed height, so it gets the docked fit instead. Growing it anyway pushed its text 556 px below the screen, more each frame.
  - **Inventory tab:** it ends above the hotbar's item rows, so items still drag onto the hotbar as in the classic layout. The other tabs fill the screen.
  - **Map tab:** the hub lets go of the `panel_open` Steam layer, so L1/R1 zoom the map as before, and the strip shows no L1/R1 badges. The map's controls step down below the strip through their own `KeepOnScreen` (new `KeepOnScreen.Avoid`); the strip covered them at 1920x1080.
  - **Closing** puts back the windows' frames, places, heights and sibling order, and the Technology inset. It also releases the `StructuredLayout` hold and the layer.
- `Steam/SteamInputBridge.cs`: a game layer turning on or off changes what a held button means. B closes a structured panel in `panel_open`; the close drops the layer while B is still down; and in the base set B is Toggle Ride Vehicle. An action that turns on within three frames of such a change now acts only after its button is released.
- `UI/UiController.cs`: `OpenTechnology`, `IsFleetPanelOpen` and `MapControlsRect` for the hub. `Localization/Labels.cs`: the tab names, with rows in all 11 locales; Inventory, Fleet and Blueprints reuse existing rows.

## Evidence

Kind: visual

| Claim | Basis | Where |
|---|---|---|
| Every tab opens in the hub, at 1280x800 and 1920x1080, with no text under 9 px on the Deck screen | MEASURED: Deck tour on a built player of ca26b15e2 with the w644 save. Steam hardware is emulated and every step is a scripted Deck button (Y, R1 x5, View, R4+L4, L1, B). 14 shots each at 1280x800 and 1920x1080, 0 failures; under-9 px texts 0 in every 1280x800 shot. | /srv/fff/review/w644-a3-hub/a3-after-1280.mp4, a3-after-1920.mp4, after-1280-sheet.png |
| One-step switching, and L1/R1 cycle the tabs (on develop R1 did nothing and the Technology key only closed Fleet) | MEASURED: the same tours (R1 steps Inventory → … → Map; L1 from Inventory wraps to Info), against develop c111d222a under the same buttons (before-1280-b2-R1-no-tab.png, b4-technology.png: nothing open) | a3-before-1280.mp4, before-1280-sheet.png |
| B closes the hub and no longer also boards a vehicle | MEASURED: the 5edc89498 tour logged "[VehicleRide] No rideable structure within reach" right after its B; with the fix 0 such lines in the 1280 and 1920 tours. `SteamInputFeedTests.TheButtonThatClosedAPanelDoesNotAlsoActWhenItsLayerGoes` failed without the fix at its no-boarding assertion and passes with it. | after-1280-h9-B-closed.png, after-1280-tour.txt |
| The Inventory tab leaves the hotbar's item rows reachable, and Crafting is whole | MEASURED: tour rect logs at 1280x800, BuildBar y 0..113 and the hub panel's bottom at 120 (1920: 0..106 and 114). The census's unreachable controls on that tab fell from 36 to 10. Crafting showed all its rows and its hint (an earlier pane cut above the ability row lost the recipe grid). | after-1280-h1-inventory.png, after-1920-h1-inventory.png |
| The map's controls clear the strip at 1920x1080 | MEASURED: rect log, MapControls top at y 1026 against the strip's bottom at 1030 (before the fix: top at 1073, under the strip) | after-1920-map-controls-crop.png |
| Classic layout unchanged | MEASURED: Y in the classic layout opens the floating Inventory and Crafting before and after using the hub, 129 texts both times | after-1280-c0-classic-inventory-first.png, after-1280-c1-classic-inventory.png |
| UI cost | MEASURED: the tour's busy time per frame, uncapped, 1.7 to 4.5 ms across all 28 shots | after-1280-tour.txt, after-1920-tour.txt |

Intended look (Ben): the round-3 mocks approved in w560 (`/srv/fff/review/w560-deck-layout-v3/`, P1-P7): "remove the extra background panel and just let the content sit in the new panel"; tab order as in spec FR-015.
Built player: yes. Windows dev players of c111d222a (develop, before) and ca26b15e2 (after), launched from the slot pool under the Deck tour.
Clips: before /srv/fff/review/w644-a3-hub/a3-before-1280.mp4 and after /srv/fff/review/w644-a3-hub/a3-after-1280.mp4 (1 fps sequences of the tours' shots in tour order. Before: frame 1 Y, frame 2 R1, frame 3 Fleet, frame 4 Technology key, frame 5 B. After: frame 1 classic Y, frames 2-8 the tabs by R1, frames 9-10 the map's R1 zoom and View, frame 11 Info, frame 12 L1 to Map, frame 13 L1 wrap, frame 14 B, frame 15 classic Y)
Looked: yes, every shot at full size; the census flags were checked by eye: 12 "clipped" blueprint names are the tiles' own ellipses, as in the classic layout; the "overlaps" are HUD texts under the opaque strip and panel.
Review: no watch_video: layout changes, no animation

Tests: FFEditorTests: StructuredHubTests (6, new), SteamInputFeedTests (incl. the new RED→GREEN case), StructuredDockTests, StructuredLayoutTests, WindowFitTests, SmallScreenLayoutTest, DeckPromptFallbackTests, ControllerPromptsTests, KeyboardBehaviourRegressionTests, TechTreeScrollExtentsTest, SelectionColumnLayoutTests and the localization row tests, on the merge with develop: 99 run, 99 passed. CI runs the full suite.
Save compatibility: none, no saved state is touched

Not verified:
- On Deck hardware: Steam hardware and the buttons are emulated by the tour's scripted Deck.
- The three-frame window assumes Steam applies a game layer within three frames, as it does on its next frame by its docs. At a Deck's lowest frame rates that's still under a quarter second, but not measured on hardware.
- On the Inventory tab the hub stops above the hotbar (to keep dragging to it), where the round-3 mock fills the screen; Ben may prefer the mock.
- At 1920x1080, 20 to 53 texts per shot measure under 9 px, the plain HUD included (the earlier 1920x1080 audit on develop showed the same). The 9 px rule is the Deck's, and at 1280x800 it's 0.
- The Info tab is the objectives list; the test save has none, so it shows only its header.
- WindowFit (w668) cut Crafting's list far more than needed when the pane was 17 px short; the hub no longer asks for that cut at 1280x800, but the cut itself is unchanged here.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

