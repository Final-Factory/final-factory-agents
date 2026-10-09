---
name: unity-ui
description: "Build and verify Final Factory's Unity uGUI screens (panels, windows, tabs, HUD, popups, the structured layout and Steam Deck sizing) so they work the way a player sees them. Covers the project's UI map, uGUI layout rules and the pitfalls that broke the w644 Deck hub (layout groups, ContentSizeFitter, anchors, scroll views, grids, canvas scaling at 1280x800, layout fights that flicker, hard-coded colours), the editor rect audit, the Deck tour with full content, and the pixel checks (scripts/deck_audit/ui_check.py: flicker, fill, style, the per-still sheet), and the whole-screen layout census with ui_layout.py (new overlaps between HUD blocks, anchored clusters drifting over 2 px, every touched panel's colour and alpha against a classic panel). Use before changing or reviewing any UI, and before calling a UI change verified."
---

# Unity UI: build it, then verify it like a player

The w644 Deck hub (#1251) passed a tour of 28 stills and broke on Ben's Deck: navy instead of the
game's teal-blue, Crafting cut to one row, no tech grid, the Blueprints preview off the bottom with
flickering icons, Factory info in a corner of its pane. Every check had asked "does it open and
fit", none "does it show everything and look like the game" (evidence-gate,
`lessons/verify-ui-with-full-content-like-a-player.md`). This skill is how to avoid that.

## 1. Know the UI you are changing

- Read the game repo's `docs/UI-Architecture.md` first: uGUI only (no UI Toolkit), scene-authored in
  `Assets/Scenes/main.unity`, `UiController` owns the HUD, panels toggle with `SetActive`. Its §3b
  is the structured layout (`Assets/Scripts/UI/Structured/`: `StructuredDock`, `StructuredHub`,
  `StationPanel`, `StructuredTabStrip`) and `UI/Components/WindowFit`, `KeepOnScreen`.
- **Canvas scale is not the screen.** `UiScaler.ScaleFactor` (`Assets/Scripts/UI/UiScaler.cs`)
  sets every HUD canvas's `scaleFactor` from the screen and the UI-scale setting (default 0.90 on
  desktop; 0.80 on a Deck, `InterfaceSettingsController.DeckUiScale`, w727, locked only in the
  structured layout: the classic layout has its slider back, w723). Below 1920x1080 the UI stops
  shrinking with the screen: at 1280x800 the canvas is about 1511x944 layout units at 0.80 and
  1343x839 at 0.90, against 2133x1200 at 1920x1080 at 0.90. Verify a Deck screen at 0.80 and 0.90,
  in both layouts (`specs/w644-deck-release/uiscale.md`: the classic layout holds to about 1.0).
- **Don't lock or hide a setting to make a layout pass.** w644 hid the Deck's UI-scale slider so the
  layout laid out at one scale; Ben gave it back to classic-layout Deck players (w723: "if a steam
  deck user isnt using structured layout then they should be able to use UI scale again").
  A window laid out for desktop gets about 70 % of its height on a Deck. Check sizes in canvas
  units at the real scale factor, never against a desktop Game view.
- **Reuse the existing look.** The classic windows' frame sprite and colours come from the scene's
  panels (`StructuredHub.Panel` copies a window's `Image` sprite, type and colour). A colour typed
  into code (`StructuredHub.Shade`'s `new Color(0.04f, 0.07f, 0.11f, 0.96f)`) is a style change the
  requester never saw. Copy the skin from the classic panel the screen replaces.
- **One owner per size.** Before you set a RectTransform's size or position, find who else does:
  its parent's layout group, a `ContentSizeFitter`, `WindowFit`, `ListGrow`, `KeepOnScreen`,
  `MaxHeightViewport`. Two owners alternate frame by frame, and that is flicker (the hub's own
  comment: "a second fit fighting it made the window jump").

The uGUI rules and the pitfalls with their fixes: [ugui-pitfalls.md](ugui-pitfalls.md).

## 2. Write down what "right" means, per screen, before the first shot

One line per screen and sub-view: the requester's words (quoted), and what full content is
("Crafting: every row of the selected category's grid"; "Technology: the tree grid with nodes";
"Blueprints: the list, and a selected blueprint's preview whole on screen"; "Factory info: its
stats filling the pane"; "the colours of the classic Inventory"). Put the words in a file for
`ui_check.py shots --words`. Without this list a still can only be checked against itself.

## 3. Check the layout in the editor while you work

In play mode, with the Game view at the target size (1280x800 for the Deck) and the screen open,
run the rect audit through `execute_code` ([rect-audit.md](rect-audit.md)). It lists, for the open
UI: graphics off screen, content cut by a mask that cannot scroll, grids showing fewer rows than
they hold, scroll views whose content cannot scroll, windows using little of their pane, and big
flat fills with their colour. Fix what it lists before you build a player. It is a quick check, not
the verdict: the verdict is a built player (section 4).

## 4. Verify in a built player, with full content

The game repo's Deck tour (`Assets/Scripts/Diagnostics/DeckTour.cs`; `docs/UI-Architecture.md`
§3b; scripts in `specs/w644-deck-release/tour/`, `scripts/deck_audit/`) drives a development player
with a scripted Deck: `-ffDeckTour <steps.json> -ffDeckTourOut <dir> -ffDeckTourSize 1280x800
[-ffDeckTourUiScale <s>] [-ffDeckTourQuit]`, launched from the slot pool
(`python scripts/nightly/player_slots.py launch <build> -- <args>`). Each `shot` saves a PNG and a
census (`<shot>.json`: small, clipped, off-screen and overlapping text, covered controls).

- **Content.** Tour a late-game world. Load one with `{"setup": "ffauto:ui.loadgame|<save name>"}`
  (the save copied into the saves folder under a name of your own, removed afterwards). To fill a
  new world: `ffauto:cheats.enable`, then `ffauto:player.devunlock` (every technology and a starter
  pack, `LocalMultiplayerAutomationCommandRunner.ExecutePlayerDevUnlock`), `ffauto:inventory.add|
  <item>|<count>` for a full inventory. `devunlock` researches everything, so a tree that is partly
  done (the common late-game case) needs a real save. A tab that is empty in the save is "not
  verified", never PASS.
- **A clean start.** Remembered window positions (`PanelLayout`, PlayerPrefs `PanelPosition.<role>`,
  `PanelLayout.cs:95,123`) make a window "placed by the player", which the layout then skips; a Mac
  player shares PlayerPrefs with the Steam install. Clear them, or say which were set, before a tour
  (GUESS whether any merged still was affected; w741's sweep found the keys, not a bad still).
- **Development overlays are not the game.** The Debug Info counters, "Agent control ON" and Graphy
  draw in a development player and show up as overlaps and flicker; `ui_layout.py` ignores them,
  `ui_check.py` does not. Hold keys by `seconds`, not frames: a frame count is gone in a blink at
  200 fps (#1258).
- **The photos' states (w764).** `specs/w764-deck-thread/` in the game repo drives the tours that reproduce a player's
  Deck photos: `make_tour.py` parts `hub`, `docked`, `classic`, `persist` (a window dragged with the `drag` step, then the
  building opened again), `reload` (a save and load, then Info), `menus` (New Game > Custom); worlds `audit` (the saved
  w644 world), `new` (a new game with the objectives card and a Command Core, wait about 75 s for the narration hold) and
  `menu`; `run_matrix.sh` runs them on two builds at 1280x800 / 0.80 and 1920x1080 / 0.90. The census has `midWord` (a word
  cut across two lines) and `shortLists` (a scrolling list that shows under 2.5 rows) beside `clipped`.
- **Every sub-view.** Per tab: select an item, hover one, open its preview or second page, scroll
  the list to the end (`at` + `press right_trigger`, `stick`). A tour that only presses R1 tests the
  tab strip.
- **Wait for content.** `{"waitFor": "text:<something only the filled screen shows>"}` before each
  `shot`, not a fixed `wait`.
- **Clips at real rate.** `{"record": "<name>", "seconds": 4}` saves every frame as JPGs in
  `clip-<name>/` (with `frames.txt` for ffmpeg). Record each screen idle and while hovering and
  selecting. Never stitch the stills into a 1 fps "clip".
- **Both arms.** The "before" is the classic screen with the same content (`{"layout": "classic"}`),
  so style and fill can be compared; develop with nothing open compares nothing.

## 5. Check the pixels, then look at every still yourself

`scripts/deck_audit/ui_check.py` in the game repo (numpy + Pillow; rects are image pixels from the
top-left, or pass `--unity-y` for a tour `rect:` log line):

```sh
python scripts/deck_audit/ui_check.py flicker <tour>/clip-hub-blueprints --rect 0,60,1280,800 --out flicker.png
python scripts/deck_audit/ui_check.py fill <tour>/h4-factory-info.png --pane 0,60,1280,790
python scripts/deck_audit/ui_check.py style <tour>/h1-inventory.png --rect 40,80,600,700 \
    --ref <tour>/c1-classic-inventory.png --ref-rect 300,150,860,770
python scripts/deck_audit/ui_check.py shots <tour> --words words.txt     # writes <tour>/shots.md
```

- `flicker`: regions that change and change back within 4 frames, twice or more. 0 is the bar.
- `fill`: the content's span of the pane and the largest empty band; under 60 % or a band over 40 %
  is flagged. It needs an opaque pane (a translucent classic window lets the world count as content).
- `style`: background colour and palette against the classic panel; delta E over 10 is flagged.
- `shots`: one row per still with its census flags. Fill in every row while looking at the still at
  full size: what it shows, whole or not, classic look or not, which of the requester's words it
  meets or breaks. That sheet is "Looked: yes".

Then the evidence-gate's [UI checklist](../evidence-gate/checklists/ui.md) and, in the PR, the
`Content:`, `Full content:`, `Style:`, `Shots:` lines and a flicker result (`pr_evidence.py`
fails a UI change without them). Publish the stills, clips and the sheet with `publish_review`, and
put the stills of every screen in front of the person who asked for the look.

## 5b. Check the rest of the screen, before and after

A change to one panel can move or cover another: the minimap's side buttons drifted off it and a
slide-out lay over the hotbar while each PR checked its own panel, and #1272's new backdrop turned
the Blueprints window opaque navy (w733). Take the layout census
([layout-census.md](layout-census.md)) on the base commit and on yours, same save and size, with
the whole HUD showing, every slide-out open and your screen on top, plus a screenshot of each, then:

```sh
python "<this skill's base directory>/ui_layout.py" check --before before.json --after after.json \
    --touched <your window> --shot after.png --ref-shot classic.png --ref-census classic.json
```

It prints the `Overlaps:`, `Opened panels:`, `Alignment:` and `Style:` lines for the PR and exits 1 on a new overlap
between always-on HUD blocks (a panel the player opens and closes may cover the HUD: Ben, w732 and w742; it
must be on top, clickable, inside the screen and give the HUD back, `--closed`), a cluster ([hud-clusters.json](hud-clusters.json)) drifting more than 2 px, or a
touched panel more than delta E 10 from the classic Inventory on screen, or with different art or
see-through. Measured in the editor at 1280x800, classic layout (w733): #1264 (121b8691b) moved the
quick buttons from 7 to 24 px off the minimap, the toggles 31 px and the hotbar 98 px, and nothing
moved after it; opening the Blueprint slide-out puts it over the hotbar (a new overlap against the
closed HUD); #1272's backdrop is delta E 23.8 from the classic Inventory on screen, where the window
was 2.1 before it.

## 5c. A font-size change, and the desktop under a Deck change

A text size change is checked text by text: the census records each text's lines, overflow and ellipsis, and
`text_diff.py` lists every text with the same string that fits before and not after ([layout-census.md](layout-census.md)).
Check fit in the runtime font: a localized text is drawn in `LocalizationHelper.ApplyFont`'s font (Khyay for Latin
locales), not the one its prefab names. A layout or size change made for the Deck is checked on desktop too
(1920x1080 and 2560x1440 at the default 0.90): the I-key windows open where they did, stay put while the pointer
crosses buildings, and a dragged window does not get another laid over it (w761, the evidence-gate UI checklist
items 15 and 16).

## Related notes

- `project-memory` → `ui-screenshot-worst-case-before-done` (Ben, 2026-09-22): longest text,
  longest locale, notice mode, everything co-visible; hidden-sibling row heights and
  `childControlHeight` traps.
- `project-memory` → `editor-ui-screenshots-at-fixed-sizes-and-locales`,
  `ui-built-in-editor-scripts-overrides-churn-tmp-height`,
  `ui-gesture-verification-virtual-mouse-and-topmost-clips`,
  `editor-host-mp-ui-worst-case-screenshots` (UI only other players see).
- `drive-game` (the canonical screenshot recipe), `watch-video` (`record_clip`, `--mode vfx`),
  `playtest`.

## 6. Not verified, said plainly

No real Deck: "Not verified: Deck hardware". No late-game save: say which tabs were empty. Never
turn a gap into a PASS by listing it under "Not verified" while the title says the screen works.
