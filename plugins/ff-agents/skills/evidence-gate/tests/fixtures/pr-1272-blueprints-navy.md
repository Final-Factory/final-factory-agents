Request: w712

Ben, with a Steam Deck screenshot: "can you make blueprint panel better fit on a steam deck too?" and "UI should be clean and flowy!". Presentation only; no simulation, save or network code.

## What changed
- **Fit (`BlueprintPanelFit`, new):** on a canvas shorter than the panel (the Deck's is 1342x839 units; the panel was 852 tall) the panel sits below the top HUD row, gets a solid backdrop (the HUD no longer shows through the frame art), and the preview image gives: it shrinks to what keeps the panel on screen, never below 150 or above 340 (it was a fixed 400, a third of the height). On a canvas with room nothing moves. In the w560 docked hub the hub places the window; the component only caps the preview.
- **Names:** tiles are 96 units wide (four per row, were 76 and five) with three lines of text, so "Mining Station All sides V2" reads whole in the tooltip and as two lines on the tile; the details name wraps (16 bold); the label column is 104 (was 90, "Date Creat…"); the breadcrumb keeps the open folder's name and collapses the middle to "…".
- **Split and flow:** details column 456 (was 416), item icon beside the name, Edit beside it, Copy Import String and Upload to Workshop share a row, Delete stays last under a divider; the browser's grid takes the leftover height; the folder bar no longer stretches.
- **Legibility:** the Folder dropdown's text 12 -> 14 (8.1 px caps in the census, under Valve's 9 px).
- Buttons are 28 high (folder row 25), text 14: the w705 floor (`UiScaler.MinLegibleFontSize`). w705/w711 changed `StationPanel` code, not a shared button style, so there was nothing to reuse.

## Evidence
Kind: visual

| Claim | Basis |
|---|---|
| On the Deck's 1342x839 canvas the panel no longer reaches over the top HUD row; the HUD under it no longer shows through | MEASURED: development players, Deck tour at 1280x800, panel top at y 60 (was 30), solid backdrop; stills `after-1280-*` against `before-1280-*` in /srv/fff/review/w712-blueprints-deck/ |
| Names read whole: tile names wrap to two or three lines with a tooltip, the details name wraps, labels are not cut ("Date Created"), the open folder keeps its name in the breadcrumb until it is very long | MEASURED: census clipped texts 9 -> 4 at 1280x800 (classic, blueprint selected), stills 02 and 05 before/after |
| Text meets Valve's 9 px capitals at 1280x800 | MEASURED: Deck tour census, texts under 9 px 1 -> 0, smallest capital 8.1 -> 9.5 px |
| 1920x1080 is no worse | MEASURED: stills `before-1920-*` / `after-1920-*`; no HUD overlap in either, frame art unchanged, the panel keeps its translucent look |
| The docked hub tab (w560) still works | MEASURED: tour reached Blueprints with R1 twice, selected a blueprint; stills 06/07 at both sizes |
| 152 UI, layout, legibility and structured-hub tests pass | MEASURED: editor run of `BlueprintPanelDropTest`, `TextLegibility*`, `Structured*`, `WindowFitTests` and the rest of `test_select.py`'s UI list, 152 of 152 |

Intended look (Ben): "UI should be clean and flowy!" and a panel that fits the Deck without the HUD showing through and without cut-off names (his screenshot of the Blueprints panel, 2026-10-08).
Built player: yes, development players run through the slot pool (before 121b8691b, after 3b807f9bf), Deck tour `-ffDeckTour`, blueprint library `-blueprintLibrary` with long names.
Clips: /srv/fff/review/w712-blueprints-deck/flow-before-1280x800.mp4 and flow-after-1280x800.mp4: open at 1 s, select a blueprint at 3 s, open the folder at 5 s and its sub-folder at 7 s, select at 9 s.
Looked: yes, stepped through frames at 1 s, 3 s, 5 s, 9 s and 12 s of the after clip: the panel opens in place below the HUD, the details column appears without moving the browser, the preview and buttons stay inside the panel; the stills for both sizes were opened one by one.
Not verified: a real Deck or a real controller (none on m5; the scripted Deck presses the tab and click flow only); a very long open-folder name still truncates in the breadcrumb (the Folder row shows the full path); the CI result (this section is written before it).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

