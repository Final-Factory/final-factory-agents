---
name: unity-ui
description: "Build and verify Final Factory's Unity uGUI screens (panels, windows, tabs, HUD, popups, the structured layout and Steam Deck sizing) so they work the way a player sees them. Covers the project's UI map, uGUI layout rules and the pitfalls that broke the w644 Deck hub (layout groups, ContentSizeFitter, anchors, scroll views, grids, canvas scaling at 1280x800, layout fights that flicker, hard-coded colours), the editor rect audit, the Deck tour with full content, and the pixel checks (scripts/deck_audit/ui_check.py: flicker, fill, style, the per-still sheet), and the whole-screen layout census with ui_layout.py (new overlaps between HUD blocks, anchored clusters drifting over 2 px, every touched panel's colour and alpha against a classic panel, every HUD element the change moved at 1920x1080, 1280x800 and 1280x800 docked, each asked for in the brief's own words, and the places Ben fixed himself pinned in hud-pins.json: move only what the person asked to move), and how a window opens (lag and a jump after it appears: the probe tour, the open hold). Use before changing or reviewing any UI, and before calling a UI change verified."
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

- **Wake a Mac's display first (w1165).** A locked Mac whose display has gone to sleep stalls every built player at start-up
  (under 1 % CPU, `tour.log` ends at `screen WxH Windowed`, the first `waitFor` times out after 10 minutes): run
  `caffeinate -u -d -i -t <seconds>` before the launch (it wakes the display; the lock can stay). Check with
  `ioreg -n Root -d1 -a | grep -A1 IOConsoleLocked` ([project-memory](../project-memory/memories/feel-measurement-traps-2026-09-27.md)).
- **Tours stay at real speed (w931).** Most agent play runs at `-ffGameSpeed 4` (drive-game, "Play faster"), but a
  tour's waits are UI settle times and its checks include a real-rate clip and flicker, which a raised speed would
  change. Add `-ffGameSpeed` only to a tour leg that waits for the game itself to progress, and take its clips at 1x.
- **The tour is not a Deck (w770).** It hands the game a scripted Deck, forces its own window size every second and
  starts from clean prefs, so it cannot show Steam's layout choice, the Proton first-frame resolution, the Steam client
  version or touch. Say "verified on a real Deck" or "not verified on a real Deck"
  ([evidence-gate deck list](../evidence-gate/checklists/deck.md)).
- **A stored size, without forcing one (w771).** `-ffDeckTourSize none -ffDeckTourPrefs '<json>'` starts the tour from
  seeded `ResolutionWidth`, `ResolutionHeight` and `FullscreenMode` and never calls `Screen.SetResolution`; read `screen`
  in `report.json`, not the census ([deck.md](../evidence-gate/checklists/deck.md)).
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
- **Judge a dropped window where it opens again, not where it was dropped (w1217).** While a window is dragged and
  after the drop it sits on the drag canvas (`PersistentObjects/Canvas/PanelShowcase`), above the whole HUD, until it
  is closed. Opened again (the next session, with its saved `PanelPosition`) it is back under `GamePanels`, where the
  Player Inventory (`MiniInventory`) and the structure windows draw before `TopInfoPanel`, the top bar. A still taken
  right after the drop cannot show a header that bar will cover: for any placement claim, run a second player with
  the saved place and measure the header's points against the topmost raycast target in that census (w1217: #1581
  let a top-left drop leave 57 of 57 header points of the Player Inventory under the top bar at 1280x800, so it could
  not be dragged out or closed by its X; the drop's own still looked fine).
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
- **The pins census needs a building with storage selected (w1064).** `pr_evidence.py` has no way out of a `Pinned:` line that reads
  "not shown", and `ui_layout.py pins` shows the Player Inventory only when it is up. With the Atomic Printer selected, `ffauto:ui.open|inventory`
  failed ("toggle ran but the panel stayed closed"), the `I` key opened it in the docked layout only, and selecting a far Assembler selected
  nothing: six tours (before and after, three sizes) went by before a **Cargo Hold selected, an Assembler hovered** gave `0 broken, 0 not
  shown` at 1920x1080, 1280x800 and docked. Start from the game repo's `specs/w1064-craft-queue-grouping/make_station_tour.py`.
- **A tour that ran `ffauto:console.run` has the dev console open over the bottom-left HUD (w1064).** A `record` clip then shows the console, not the
  queue or panel. Take a `shot` first (it closes the console); the frames of a tour clip at 1920x1080 ran at about 75 fps, so check
  `frames.txt` before calling a clip real-rate. `make_tour.py --clip` in the same folder does it.
- **A tutorial step is reached by a save, not by a count of skips (w883).** `ffauto:console.run|completeXObjectives 1` once
  per step advances at the heartbeat, not per call: 34 calls landed on the assembler step in one run and on "Open the map"
  in the next, and `completeXObjectives 33` in one call only completes the first. Skip once with a save after each call
  (`ffauto:ui.savegame|<name>-<i>` plus the `observe.state|objectives` line before it), pick the save whose logged step is
  the one you need, name the saves `ffa-<session>-<name>-<i>` (your `$TMPDIR` folder's name in front) so you can `rm -f` the rest from the saves folder with no approval, and load it with `-ffAutomationSave <name> -ffAutomationRole
  solo` for every before/after run (`specs/w819-craft-hint-border/make_tour.py --save-from`, `run_tour.sh` with `SAVE=`).
  A save made by skipping also shows what a player who skipped sees: the research steps leave their techs unlearned.
- **Wait for content.** `{"waitFor": "text:<something only the filled screen shows>"}` before each
  `shot`, not a fixed `wait`.
- **Clips at real rate.** `{"record": "<name>", "seconds": 4}` saves every frame as JPGs in
  `clip-<name>/` (with `frames.txt` for ffmpeg). Record each screen idle and while hovering and
  selecting. Never stitch the stills into a 1 fps "clip".
  The frames come out **upside down** (w819: every `clip-*/NNNNN.jpg` is flipped vertically; the
  `shot` PNGs are not), so crop and `ui_check.py flicker --rect` in flipped coordinates, and make
  the video with `cd clip-<name> && ffmpeg -f concat -safe 0 -i frames.txt -vf vflip -c:v libx264
  -pix_fmt yuv420p out.mp4`. `pr_evidence.py` only accepts a `Clips:` line that names `.mp4` files
  (with where the event is, "0 to 3 s"), so encode the before and after clips and publish them.
- **Two steps that did not do what they look like (w902, Windows development player).** (1) The title menu's Early Access notice (`PreAlphaNotice`) stayed up after `pressUntil button_menu` and after `key Escape`, and covered New Game; click `name:Continue/FFButton` first. (2) With a station selected in the classic layout, the `T` key did not open the Technology window (`selectTech` then fails: "the technology panel is not open"); hold Esc to deselect, then `{"setup": "ffauto:ui.open|technology"}`, in both layouts. Selecting a building with storage opens the Player Inventory with it, so a `ui.open|inventory` after the selection toggles it shut ("did not open"). The whole-UI tour that uses all three: the game repo's `specs/w902-ui-check/make_tour.py`.
- **Capturing on a shared Windows PC (w803).** Several sandboxes' players run at once, so: (1) the title menu and New Game > Custom come from a Deck tour (`click` steps on `text:New Game`, `text:Custom`; the w764 `menus` part already does it): the agent channel refuses commands at the menu (`state_not_playable`) and posted mouse messages are ignored while the window has no focus, so do not hand-click the title screen. (2) `scripts/agent/peer.py` keys the players by role, so with other sandboxes' players up its `client` is often someone else's: read your own `AgentControl/session-<pid>.json` (port, token) and call the channel yourself. (3) `record_clip.py` fails there (it picks nvenc, which an Intel GPU lacks, and ddagrab grabs the whole desktop with other players' windows over yours): record with the tour's `record` step instead. (4) The channel serves 2 screenshots a second (HTTP 429 beyond), so a screenshot sequence is at most a 2 fps timelapse, never a clip for `pr_evidence.py`; say its fps.
- **Three more tour and census traps (w1046).** (1) A `scroll` step's sign: negative `notches` scroll a list DOWN (the tour presses `left_bumper`), positive ones up; `"notches": 6` on a list at its top does nothing. (2) The `Player Inventory` pin in `hud-pins.json` is `MiniInventory`, the side panel that opens when a building with storage (a Cargo Hold) is selected; `ffauto:ui.open|inventory` opens the big Inventory and Crafting window (`InvAndCraft`) instead, so a census for `pins` selects a storage building. (3) A window's text box wider than the window (an invisible overflow) counts as a window overlap and catches clicks on the window beside it; a `RectMask2D` on its container clears both without changing any rect (`ui_layout.py moves` compares the unclipped rects, `overlaps` the clipped ones), while resizing the box shows as a move nobody asked for (the Station Grid window's Transmitters header, FinalFactory #1546).
- **A row added to a scene-sized panel, and a census that must say "HUD restored: yes" (w1145).** (1) A panel's rows are not always sized by their layout group: the scene gave the Blueprints folder bar a `LayoutElement` of a fixed height, so a second button row drew over the tile grid in the first built player (the editor-free fix: grow that element by the new row in the bar's own `Awake`; HubLayouts must size the new row's buttons too). Look at the first built-player still of the 1920 leg before running the rest. (2) `ffauto:ui.open|blueprints` fails ("panel stayed closed") while a building is selected: take the Blueprints census and the station/pins census as two separate tours. (3) The HandHoldy world has an animated `RedAlertFrame` that `ui_layout.py check --closed` always reports "not where it was" (the base build too), so `pr_evidence.py` never gets "HUD restored on close: yes" from it: take the open/close census in a plain new game (`-ffSoloNewGame <name> --no-tutorial`, no placements). (4) `click` selectors take `#N` only on `text:`, and a tile's name label is not the button (`text:Defense` pressed nothing): click `name:FolderTile`, or `at` the tile then `hold`/`wait 0.12`/`unhold` `right_trigger`; a back button with only an icon is `name:Back`, not `text:Back`. (5) A player string naming a key ("Ctrl+V") fails `ControllerGlyphCoverageTests.NoTextInAnyLocaleNamesAKeyWithGlyphsOn`: say "paste". The game repo's `specs/w1145-blueprint-folder-share/` holds the tours.
- **Census-tour traps of a base-against-develop run (w1124).** (1) `ffauto:ui.menu|close` does not close a panel opened with
  `ffauto:ui.open`: the next `ui.open`'s toggle closes the open one and reports "did not open" (fleet, production and info
  failed in alternation); close each with `ffauto:ui.close|<panel>`. (2) A base build from before the w1097 settings move keeps
  display settings in shared PlayerPrefs: three such players started at once overwrote each other's `-ffDeckTourPrefs`
  resolution and the 1280x800 censuses came out 1920x1080. Run them one at a time and read `"screen"` in every census before
  comparing. (3) `scrollto:SaveLoadPanel/...` matches the multiplayer `P2_SaveLoadPanel` first; write
  `PanelsParent/SaveLoadPanel/...`. (4) The Load list sorts by each save's stored date, so a copied fixture lands mid-list and
  `click text:` fails off screen: scan the list with `scrollto` and a census at 41 places first (the game repo's
  `specs/w1124-hud-regress/make_load_scan.py`). (5) In a seed with enemies near a tour's "far" spot the ship dies there, which
  hides the station strip in one build's census and not the other's; compare in a seed where it lives (w961's).
- **A tour's pointer, three traps (w957, w959).** (1) `{"at": "x,y"}` counts y from the BOTTOM of the screen (as `drag` does, `docs/UI-Architecture.md`): a marker seen at pixel (1094, 688) from the top is `0.57,0.363`; clicking `0.637` hit empty space and looked like a hit-test bug for four builds. Read a target's pixel from the census/`rect:` line (bottom-origin) and divide. (2) A `press` of fewer than about 3 frames never reaches the game (the Deck bridge polls the held state once a frame, and the clip recorder runs a dev player at 15 fps): click with `hold`, `wait 0.08`, `unhold`; two of those are a 0.3 s double-click at 15 fps. Run a double-click leg alone: three players on one PC run at 9 fps. (3) A scripted pointer cannot pan the map: `WorldMapControlAction.UpdateDragPan` and `UiHelper.IsPointerOverInteractiveUi()` read `Input.mousePosition` (the real mouse), so a `drag` step moves nothing; say "drag-pan not shown" rather than showing a still where nothing moved. A new player-facing pointer reader should use `AutomationPointer.MousePosition`, so a tour can drive it.
- **The tour needs a development player, and its setups do not wait (w1231, biscuit Linux).** (1) `-ffDeckTour` arms only
  when `Debug.isDebugBuild` (`DeckTour.Arm`): a player from `Editor.ReleaseBuild.Build` ignores the flag without a word
  (one 6-minute build wasted). On Linux build the tour player with `-buildTarget StandaloneLinux64 -executeMethod
  Editor.LocalMultiplayerVerificationBuild.BuildLinuxMultiplayerDev -ffVerificationBuildOutput <dir>/player/finalfactory.x86_64`
  (about 6 min warm on biscuit). (2) `{"setup": "ffauto:heartbeats|N"}` does not hold the tour: the next setup runs in the same
  frame, so `hauler.addstop` right after `blueprint.place` was rejected (the station is made only when the placed core comes into
  play) and the stop list came up empty; put `{"wait": 6}` after a placement. (3) `ui.selecttile` finds a station's Command Core
  only while it stands on its tile (a flying core is on no tile): select and name stations while they are parked, then switch
  transit on. The game repo's `specs/w1231-named-waypoints/make_tour.py` does all three.
- **Flying the ship in a tour (w1059).** The tour's `{"stick": "x,y", "seconds": N}` step does not fly the ship in a built Windows development player: 5 s of stick left it at 0,-45 (the minimap's coordinates, before and after). Use `{"setup": "ffauto:movement.hold|<x>|<z>|<seconds>"}` and a `wait` of the seconds plus 0.5, and `ffauto:camera.zoom|<distance>` (50 to 300) for zoomed-in and zoomed-out shots. A world marker's tour flies the ship until its target is on screen, then away so it is off screen, and records the flight back (the game repo's `specs/w1059-objective-marker/make_tour.py`). Park the pointer (`{"at": ...}`) on empty space first: over an asteroid it brings up the hover card and brackets.
- **A bare row over the map has no panel to take a delta E from.** `Style:` then compares the one touched control (its mean colour before and after, from the stills) and quotes the removal as asked; `pr_evidence.py` skips a `Style:` line shorter than 15 characters, so do not write a bare `n/a` to dodge it. The map view is a `backdrops` entry in `hud-clusters.json` (w959): what lies on a full-screen view is not an overlap with it.
- **Both arms.** The "before" is the classic screen with the same content (`{"layout": "classic"}`),
  so style and fill can be compared; the base branch with nothing open compares nothing.

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

It prints the `Overlaps:`, `Window overlaps:`, `Opened panels:`, `Alignment:` and `Style:` lines for the PR and exits 1 on a new overlap
between always-on HUD blocks (a panel the player opens and closes may cover the HUD: Ben, w732 and w742; it
must be on top, clickable, inside the screen and give the HUD back, `--closed`), a cluster ([hud-clusters.json](hud-clusters.json)) drifting more than 2 px, or a
touched panel more than delta E 10 from the classic Inventory on screen, or with different art or
see-through. Measured in the editor at 1280x800, classic layout (w733): #1264 (121b8691b) moved the
quick buttons from 7 to 24 px off the minimap, the toggles 31 px and the hotbar 98 px, and nothing
moved after it; opening the Blueprint slide-out puts it over the hotbar (a new overlap against the
closed HUD); #1272's backdrop is delta E 23.8 from the classic Inventory on screen, where the window
was 2.1 before it.

**Windows count too (w981).** `Overlaps:` is the always-on HUD blocks. Every open window (the Player Inventory, a Cargo Hold,
Station Core or Grid panel, the Station strip, a slide-out) against the other windows and the HUD is the `Window overlaps:`
line, and `ui_layout.py overlaps <census.json>` lists them for one census, each pair named with both elements and the overlap
rect, NOT ALLOWED unless [hud-clusters.json](hud-clusters.json) `windowOverlaps` holds the requester's words for that pair
(Ben, w873: "yes put the station panel controls above station info and it should be over the player inventory", only while the
strip stands above Station Info). Take the census with the windows in reach open (a Cargo Hold or Command Core selected).
A new overlap or one kept between windows you moved fails; never measure rects by hand and call a window overlap clean
(w961's strip stood 11 px over the Player Inventory and the HUD-block count said 0).

**Then list what moved, and check the pins, on every screen and layout** (w826, w894). **Move only what the person
asked to move**: never move, re-anchor, restack or regroup an existing panel, HUD element or hover panel unless the brief
quotes the person asking for that exact element to move (Ben, after four corrections: "stop moving panels around that I
don't ask you to move around"). Take the before and after censuses at 1920x1080 (UI 0.9), 1280x800 (UI 0.8) and
1280x800 docked, a station selected so Station Info and the building hover card are up, then:

```sh
python "<this skill's base directory>/ui_layout.py" moves --pair b-1920.json a-1920.json \
    --pair b-1280.json a-1280.json --pair b-docked.json a-docked.json
python "<this skill's base directory>/ui_layout.py" pins a-1920.json a-1280.json a-docked.json
```

`moves` prints the `Moved:` line and one line per HUD block that moved or resized more than 4 px, labelled with its
screen and layout. Mark each `asked (Ben): "his words"` from inside the brief's quotation marks, naming that element on
that screen, or put the element back; there is no "justified". `pins` checks the places Ben fixed himself
([hud-pins.json](hud-pins.json): Station Info just above the abilities, the hover card just above the minimap, the Player
Inventory off the left edge) in every census, whatever the parent looked like. Measured (editor): #1282 moved Station Info
x -312, y -736 px at 1920x1080; on develop 9798f308c the docked layout breaks the Station Info and hover card pins, and
the undocked layouts keep all three.

## 5c. A font-size change, and the desktop under a Deck change

A text size change is checked text by text: the census records each text's lines, overflow and ellipsis, and
`text_diff.py` lists every text with the same string that fits before and not after ([layout-census.md](layout-census.md)).
Check fit in the runtime font: a localized text is drawn in `LocalizationHelper.ApplyFont`'s font (Khyay for Latin
locales), not the one its prefab names. A layout or size change made for the Deck is checked on desktop too
(1920x1080 and 2560x1440 at the default 0.90): the I-key windows open where they did, stay put while the pointer
crosses buildings, and a dragged window does not get another laid over it (w761, the evidence-gate UI checklist
items 15 and 16).

## 5d. How a window opens: lag and jumps (w1155)

Ben, 2026-10-12: "they are often either laggy, or the appear then shift to a new position suddenly just after appearing".
A still taken a second after the open cannot show either. Measure the open itself, frame by frame, in a built player:

- **The probe tour.** The game repo's `specs/w1155-panel-open/` (`make_tour.py`, `run_tour.sh`): the Deck tour's `probe`
  step (`PanelOpenProbe`) follows every window an input brings up at the end of every frame, and `panel_open_report.py`
  gives per window the lag (frames and ms from the input to its first drawn frame), the jump (the largest distance any
  edge stood, on a drawn frame, from where it settled) and how far a second open settled from the first; `compare.py`
  the before/after table, `make_review.py` side-by-side clips and time-labelled frame strips. The nightly lane
  `UI-w1155-panel-open` runs it. Before w1155: a Command Core's window 910 px, the Station strip 1104 px, the Player
  Inventory beside a Mass Driver at three places in three frames.
- **A window you add or place gets `PanelOpenAnimation`** (`Ensure`, or a `Header`), and its placer settles it on the
  frame it opens: since #1620 the selection column, the dock and the hub run up to 4 more passes on the open frame
  (lay out, refresh what they keep off, fill rows, refit capped lists, lay windows out from their layout roots, place
  again) until nothing moves, mark a window they place `PlacesItself` and `Unsettled` when the passes did not settle.
  The hold until still is only the net. Something that writes the window's group alpha every frame must leave it to
  the fade while it plays.
- **Hiding a jump by holding the window costs frames: measure the lag too.** #1585 held each window until it stood
  still: 0 px jumps, but a building's windows came 3-4 frames after the click where they had come in 1, Technology 2-3,
  up to 460 ms (Ben noticed; master 80403eb, built players). Report lag frames and ms from the input next to every jump
  table, before and after, and keep the nightly lane's lag budget at 2 frames. The probe counts a click from the
  button's release (the tour holds it 8 frames first); a frame's `unscaledDeltaTime` is the length of the frame before.
- **`Canvas.ForceUpdateCanvases()` only redoes layouts marked dirty**, and it raises `Canvas.willRenderCanvases` in the
  middle of LateUpdate. A pass that measures a window after it gets a stale size (a Command Core's window 419 units,
  393 drawn): lay the window out from its topmost parent with a layout group (`PanelOpenAnimation.LayOut`). A
  once-a-frame check in `willRenderCanvases` acts only after a late (order 32767) LateUpdate has run that frame.
- **A window that jumps a frame late: trace it, then switch parts off.** `-ffPanelTrace` (development player) logs
  where each opening window stands at the start of Update, of LateUpdate, at its end and at the draw, with the placers'
  passes: the stage that moved it names the kind of script. To find which part of a change moves a path-dependent
  window, build ONE player with a command-line switch per part (`-ff<id>Off=a,b`, a diagnostic commit you revert) and
  run the census per switch and per subset (about 70 s each) instead of bisecting commits (25 min a build): w1155 found
  that two open-frame layouts together, not either alone, moved the Player Inventory beside a Cargo Hold 107 px.
- **Do not fix a jump by laying the canvases out before the placers** (`Canvas.ForceUpdateCanvases()` on the open frame):
  w1155 tried it, and the path-dependent classic packer settled the Player Inventory beside a Cargo Hold 107 px lower at
  1280x800, a move nobody asked for (`ui_layout.py moves` caught it; three before censuses agreed, a build without the
  pass put it back). Take the census before and after any change to when or how a placer runs.
- **Look at the lag in ms, not only frames.** The hold costs a frame, and the frame after a selection is often a 100-200
  ms one (the panels' first update): say so, measured, beside the jumps it removes.
- `Canvas.willRenderCanvases` runs more than once a frame in the editor (Game and Scene views): a once-a-frame check in
  it keys on `Time.frameCount`, or two looks in one frame always agree.

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
