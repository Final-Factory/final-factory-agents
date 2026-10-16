---
name: mac-player-before-after-ui-tour
description: A before/after UI proof from two built Mac dev players with the DeckTour (w1386, m5, 2026-10-15) - record frames are upside down on the Mac too, macOS has no `timeout`, the pin census needs a Cargo Hold selected with the pointer on it, and ui_layout.py's on-screen Style delta E averages a window's content
---

# A before/after UI proof from two built Mac players

w1386 proved PR #1813 (the Circuit view left half-built copies under a window's Main side) with
the same tour on a Mac player of master and one of the PR head. Scripts:
`/srv/fff/review/w1386-circuit-leftovers/make_w1386_circuit_leftovers_tour.py.txt` (a flat-map
world from two ValidationScenarios blueprints, `ffauto:` setups, `record`, `shot`).

**Two players, eight minutes each.** `scripts/nightly/build_player.sh <worktree> <sha> mac
$TMPDIR/builds` built each in about 8 minutes on the m5 (measured 23:30:39 to 23:38:41 UTC). The
script needs the worktree AT the sha with the editor stopped: for "before", `switch_branch`
to a new branch with `create_from=<base sha>`. Keep the tour generator outside `Assets/` and
outside the tree (it restores tracked files and refuses untracked work in the build).

**Bound the launch: macOS has no `timeout` or `gtimeout`.** `timeout -s TERM 420 ...` exits 127 and
nothing runs. Use `perl -e "alarm 420; exec @ARGV" -- python3 scripts/nightly/player_slots.py launch
<app> -- ... -ffDeckTourQuit -ffSoloQuitAfterSeconds 400`.

**Frames come out upside down on the Mac player too.** `clip_video.py` names Linux and Windows; the
Mac dev player's `record` JPGs are flipped as well (the HUD's top bar is at the bottom of each
frame). Encode with `ffmpeg -vf vflip`, and flip `ui_check.py flicker --rect` (y = height - y). The
`shot` PNGs are upright.

**The three standard screens.** One launch per screen: `-ffDeckTourSize 1920x1080
-ffDeckTourUiScale 0.9`, `1280x800 0.8`, and `1280x800 0.8` with `{"layout": "docked"}`. Docked, a
structure window's extra view is a TAB of the dock's strip (`text:Circuit`, `text:<window title>`),
not the window's header button (`name:CircuitButtonIcon`), so the click steps differ per layout.

**The pin census (`ui_layout.py pins`, 0 not shown).** Select a Cargo Hold and put the pointer on
it: `ffauto:ui.selecttile|x|z`, `ffauto:pointer.moveto|x|z`, wait, `shot`. That opens the Player
Inventory beside it and the hover card, with Station Info up. What did NOT work: `ffauto:ui.open|
inventory` while a structure window is open ("did not open"), `ui.open|playerinventory` ("opens with a
selected building's panel"), and Y (it deselected the structure in classic and left the inventory
over the dock's tab strip docked).

**Moves against a broken "before".** `ui_layout.py moves` between master and the fix after the
reproduction steps lists the window the bug grew and pushed. Compare the same steps where both
builds behave alike (the window open, the pin census) for the `Moved:` line, and run `moves`
between each build's OWN stills before and after the steps: master moved the Light window -248/+327 px
and grew it 654 px, the fix moved nothing. Say both in the PR.

**Style: background, not on-screen mean.** `ui_layout.py check --touched <window> --ref MiniInventory
--ref-census <a census with it open>` printed delta E 12.3 for an unchanged window (same sprite
`background-main`, #FFFFFFFF, alpha 1.00): it averages the window's content (here the Circuit view's
pale condition row, 15 % #cccccc). `ui_check.py style <shot> --rect ... --ref <shot> --ref-rect ...`
separates the background: delta E 4.2. Both need Pillow (and numpy): `python3 -m venv $TMPDIR/venv &&
$TMPDIR/venv/bin/pip install pillow numpy`, then run them with that python.

Related: [[built-mac-player-ui-capture-resolution-and-clips]], [[built-player-esc-menu-ui-tours-and-clips]]
