Request: w873

**TL;DR:** the station controls panel (rotate / Move / Land, Copy, Deconstruct, Hide panels) no longer sits over the objectives card. It stands where the action bar's old Copy / Deconstruct buttons were, next to the abilities, with no header, "Copy" and "Deconstruct" as labels, Hide panels in the Copy / Deconstruct row, and the "Research Mobile Stations to unlock" line above the flight buttons it is about.

Ben (w873): "The station controls panel shouldn't appear over the objectives by default. It needs a better spot,maybe just down where the old copy and deconstruct buttons were next to the abilities. Change the copy station to copy and deconstruct station to deconstruct to shorten it. Then move hide panels to that row. That should compact the width of the panel. And just remove the header to get rid of vertical space." and: "move this text above the buttons since its confusing it looks like its applying to the copy and deconstruct. especially now that we are getting rid of the header".

## What changed

- `StationStripSpot` and the new `StationStripPlacement`: the panel's bottom-left corner is the corner of `ActionBarParent/BlueprintActions`, growing upward. It stands right of the Station Info box where that box reaches into its row, drops the Hide panels word when the minimap's buttons leave less room, and on a Deck's classic layout (244 units of room, 447 needed) stands on the other side of the ability row.
- `StationPanel`: no header (no title, no "Max speed" line). Rows: unlock line, rotate / Move / rotate | Land, then Copy / Deconstruct / Hide panels. Labels are `Labels.Copy` and `Labels.Deconstruct`, keys all 11 languages already translate (no new localization rows). The action bar's own buttons and the confirmation dialog keep "Copy Station" / "Deconstruct Station".
- `SelectionColumn` and `StructuredDock` use the new spot; the dock stops its column and inventory above the panel; nothing keeps off the top-left corner any more. Merged with w874's Move/Land fix: the panel closes during Move/Land and the legacy buttons stay hidden (`StationButtonsHiddenDuringCommandTest` passes).
- Docs: `docs/UI-Architecture.md`.

## Evidence

Kind: ui

| Claim | Basis | Where |
|---|---|---|
| The panel is off the objectives card at 1920x1080 and 1280x800, classic and docked, English and German | MEASURED: built Windows development players (before = develop 7c8a19f73, after = f0437d8cc), Deck tour at 1920x1080 UI 0.9 and 1280x800 UI 0.8, 12 runs per build; `ui_layout.py check`: 0 new overlaps | /srv/fff/review/w873-station-controls-final |
| It is narrower: 447 / 497 units (English / German) at the Deck, was 514 / 625; 391 px at 1920x1080, was 452 | MEASURED: layout census of the same tour before and after | tour layout.json files |
| Height is 108 units locked and 83 unlocked, whatever is selected | MEASURED: census; `StationStripSizesTest` | |
| No flicker | MEASURED: `ui_check.py flicker` on 5 real-rate clips (frame spacing 15-17 ms): 0 regions each | clips below |
| Copy, Deconstruct and Hide panels fit in German | MEASURED: German stills at all four size/layout pairs; the census flags no text of the panel as clipped or overlapped | stills |

Intended look (Ben): "just down where the old copy and deconstruct buttons were next to the abilities"; "just remove the header"; "move hide panels to that row. That should compact the width of the panel"; "move this text above the buttons"
Built player: yes (Windows development player, launched through `scripts/nightly/player_slots.py`)
Clips: after-1920-classic-idle.mp4 (idle, 0-3 s), after-1280-classic-idle.mp4 (idle, 0-3 s), after-1280-docked-idle.mp4 (idle, 0-3 s), after-1280-docked-toggle.mp4 and after-1920-classic-toggle.mp4 (Hide panels pressed and pressed again, 0-8 s), 60 fps; ui_check flicker: 0 regions
Flicker: 0 regions in every clip (the panel's rect, and for the first clip the whole screen)
Looked: yes, each still at full size (Shots)
Review: no blind model review

Content: not a late-game save. A new game with the tutorial objectives card up (`-ffSoloObjectives HandHoldy`), one station from the w722 blueprint (fixed, so the flight row shows disabled), and the flying-station fixture `ValidationScenarios/mobilestations/station-belts.ffbp.txt` (flight row enabled; Hide / Show panels pressed). The panel's content is a fixed set of rows, not a list that grows.
Full content: every row shows whole in every still: the unlock line while locked, rotate / Move / rotate | Land, Copy / Deconstruct / Hide panels (Show panels alone when hidden). No text of the panel is clipped or overlapped in any of the after stills.
Style: SelectionColumnStrip (touched) vs MiniInventory (the classic Inventory window), 1280x800 classic: delta E 0.0 (tint), alpha 1.00 vs 1.00, art 'background-main-opaque' (the Technology window frame the panel has always copied, `TechnologyWindowFrame`) vs 'background-main'; StructuredStation (docked): delta E 0.0 (tint), alpha 1.00 vs 1.00, same art as the strip.
Style note: sampling the screenshots (`--shot`) reads 15.4 to 19.2 for the same panel against the Inventory at the Deck (13.3 to 28.5 docked) because the panel is see-through and now stands over the bright nebula at the bottom of the screen, where the Inventory and Cargo Hold are over dark sky. The unchanged Cargo Hold and hover card read 10.1 to 10.5 against the same Inventory over that backdrop, and the panel read 6.9 at its old top-left spot over dark sky. No colour, alpha or sprite of the panel changed in this PR.
Overlaps: 0 block pairs before, 0 after, 0 new, 0 kept between blocks the change moved (ui_layout.py, whole screen, block depth 2); 0 opened-panel pair(s) over the HUD, not counted here
Opened panels: 0 opened panel pair(s) over the HUD (allowed: Ben, w732 and w742), 0 under the HUD, 0 not clickable, 0 cut off by the screen edge, HUD restored on close: yes (0 covered HUD element(s) checked in the closed census) [1920x1080 classic and docked, 1280x800 docked, and 1280x800 classic in the pre-merge run; in the post-merge 1280x800 classic run the Cargo Hold stood over the objectives card's lower edge, which w813 allows, and the tool's "not restored" there was the card's pulsing red alert border, not the panel]
Alignment: max drift 0 px over the clusters (bottom-right HUD, top-left HUD); tolerance 2 px
Moved: 6 element move(s) over 4 px at 1920x1080, 1280x800 (ui_layout.py moves, the same save and screens before and after)
- 1920x1080 GamePanels/SelectionColumnStrip (classic): x +1084, y +803 px, size -61 x -23 px (was 4,59 452x119, now 1118,874 391x96): asked (Ben): "just down where the old copy and deconstruct buttons were next to the abilities"
- 1920x1080 GamePanels/StructuredStation (docked): x +1045, y +799 px, size -61 x -23 px (was 11,63 452x119, now 1087,874 391x96): asked (Ben): "just down where the old copy and deconstruct buttons were next to the abilities"
- 1280x800 GamePanels/SelectionColumnStrip (classic): x +113, y +634 px, size -58 x -22 px (was 3,56 432x112, now 145,701 374x90): asked (Ben): "just down where the old copy and deconstruct buttons were next to the abilities"
- 1280x800 GamePanels/StructuredStation (docked): x +720, y +629 px, size -58 x -22 px (was 10,59 432x112, now 759,699 374x90): asked (Ben): "just down where the old copy and deconstruct buttons were next to the abilities"
- 1280x800 GamePanels/MiniInventory and CargoEntityPanel (classic): the inventory x +359, y -217 px, the Cargo Hold x -81, y -31 px: not asked: justified: the classic packer placed them around the strip's old top-left corner and now keeps clear of its new spot, which lies over the inventory's old bottom edge
- 1280x800 GamePanels/MiniInventory, HoverDescription and BuildInfoPanel (docked): each y -119 px: not asked: justified: the docked cluster stood under the strip in the top-left corner; with the strip gone it stands at the top, as it does on a desktop (`DockedInfo.Place`)
Shots: /srv/fff/review/w873-station-controls-final/ (stills and note.md: desktop and Deck, classic and docked, English, German, locked and unlocked, a flying station with Hide / Show panels)
Real Deck: not verified on a real Deck: the tour is a scripted Deck on a Windows PC; Ben checks a real Deck after it ships (Steam client and SteamOS versions, touch and the layout choice stay open)

Tests: FFEditorTests (test_select.py selection, 179 classes) 1275 run, 1275 passed, 0 failed; after the develop merge the touched classes (83 tests) again 0 failed
Save compatibility: none, no saved state is touched
Not verified: a real Steam Deck; a late-game save; a multiplayer client; the "Max speed" readout is gone with the header and nothing replaces it; on the Deck's classic layout the panel stands left of the abilities, not right of them.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
