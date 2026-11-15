---
name: ffu-ui
description: Build and verify UI in Final Factory Universe (FFU), the Rust engine in Final-Factory/ffu - `ffu-ui`'s retained tree as data (roles, bounds, Tab order, the arrow focus graph, the accesskit tree), the agent API's `ui_tree`, headless stills of a panel at several sizes, its bounds, focus, minimum text size and locale tests, and buttons that submit sim ops. Use before changing or reviewing any FFU panel, inspector or HUD, and before calling a UI change verified; it replaces unity-ui there.
---

# UI in FFU

FFU's UI is data: `crates/ffu-ui` lays out a tree (taffy for layout, parley for text) whose every node has a role,
a name, its text, its bounds, its font size and its place in the focus graph, and draws it through `ffu-render`.
An agent reads the tree as JSON instead of guessing from pixels, and checks a still only for how it looks.
`/ff-agents:ffu-build-test` sets up the toolchain.

## Read the tree

```sh
cargo build --release -p ffu-headless --features agent-api
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"ui_tree","params":{"index":10,"width":1280,"height":800}}' \
  | $B/ffu-headless serve --start factory:2000:1
```

- `ui_tree` takes `width` and `height` (16 to 4096, default 1920x1080) and a building by `{index}` or `{x, y}`, which
  opens its inspector; with neither it answers the bare screen. It never changes the sector.
- The answer holds `width`, `height`, `scale`, `nodes`, `focus_order`, `focus_graph`, `tick` and `open`. Each node
  has `id`, `role` (screen, panel, row, heading, label, value, progress_bar, button), `name` (a stable id such as
  `inspector.remove`), `text`, `bounds`, `font_px`, `text_bounds`, `fill`, `value`, `focus`, `parent` and `children`.
- Ask questions of the JSON: is every button inside its panel at 1280x800, does Tab reach each button once, is any
  `font_px` under 9. That is the census; a still is not.
- Through `ffu-mcp` the same call is the `ffu_ui_tree` tool. `ui_tree` lays out in English: the agent API has no
  locale yet, so other locales are checked by the tests below.

## Look at it

```sh
cargo run --release -p ffu-ui --example inspector -- "$OUT" 1280x800 1920x1080 3840x2160
```

It lays out the first crafter's inspector of `factory:2000:1` after 480 ticks and writes `inspector-<W>x<H>.json` and
`.png` per size, one JSON line each. Measured on lothdesktop (w2895, ffu main 821bcea, Arc B580 on Vulkan): 29 nodes
at 1280x800. `capture` (the agent API) draws the sector, not the UI. Show a person a still only after the tree's
checks pass, and judge it by the evidence-gate's UI checklist (`/ff-agents:evidence-gate`, `checklists/ui.md`): the
design gate, a fresh `ui-critic` agent on the stills, and **move only what the person asked to move**. A new panel or
screen starts before all this, with a design and mocks beside FF1's equivalent window for the person's pick, and no
code until they pick (UI checklist item 0, w2895 and w4008; FP.21's 32 pages of identical buttons were the miss).

- **A still of an opened panel from the built client** (w2895, ffu #652): `ffu --start world.snap --still out.png
  --inspect X,Y --press A,B` opens the inspector of the building at X,Y and presses the named nodes in order before
  the still. The FF1 world: `ffu-headless ff1 import tools/world/ff1-trailer-staging-0.50.0.54.zip`.
- **Before each critic round, check every tile in a row has one width in every still**: ui-critic round 4 of FP.21
  graded the hold grid BROKEN for closed slots narrower than open ones.

## The tests a UI change keeps green

```sh
cargo test --release -p ffu-ui
```

- `tests/bounds.rs`: `check_tree` (the root is the screen, every node has area and stays inside the screen and its
  parent, text at least 9 px), `check_focus` (only buttons take focus, Tab wraps, arrows reach every node) and
  `check_access` (the accesskit tree matches), at 1280x800, 1920x1080 and 3840x2160 and in every one of FF1's 11
  locales (en, de, es, fr, it, ja, ko, pt-BR, ru, uk, zh); `every_locale_draws_every_character` fails a glyph a
  bundled font lacks. Two tests plant text too wide for its box and text under 9 px, to prove the checks fail.
- `tests/press.rs`: Remove submits a remove and the building is gone the next tick; Rotate turns it, keeping kind and
  parameter; four rotates come back to the start; Close and a click off the buttons submit nothing.
- A new panel gets the same: lay it out with `layout_in(spec, width, height, locale)` for each locale (the
  inspector's spec is `inspector_in`), run `tests/bounds.rs`'s `check_tree`, `check_focus` and `check_access` helpers
  on it at the three sizes, and give each button a press test.
- **A disabled control is a Row, not a dimmed Button** (w3968, ffu #656). `tests/gate.rs`'s
  `every_panel_passes_the_ui_gate` holds every `Role::Button` to taking focus. A pager arrow at the last page drawn as
  a dimmed, unfocusable Button failed it 66 times ("button hold.prev takes no focus"). Draw it with `role = Role::Row`,
  `focusable = false`, fill `BAR_BACK` and `ink(.., MUTED)` (the shared `wreck::pager`), and make its press return
  `None`.
- **Example stills use real items** (`ffu_sim::content` constants), never made-up ids: the wreck example's ids `100 +
  slot * 5` drew whatever items those ids happen to be, which a critic reads as a wrong panel (w3968).
- New visible text goes into `crates/ffu-ui/src/locale.rs` with every locale's string. A CJK character outside the
  cut fonts means re-cutting them with `tools/subset_cjk_fonts.py`.

## Buttons are ops

A button never writes the sector. `UiTree::hit(x, y)` finds the focusable node under a click, `press` turns it into
ops and `submit` queues them through `Sector::submit` for the next tick, the same path as every other mutation
(`/ff-agents:ffu-add-op`). Rotate is a remove and a place in one tick. Prove a button by its press test: press, one
step, then the sector shows the change.

- **A still of the HUD's pilot parts (the fleet card, speed) comes from a clip, losslessly** (w4260, ffu #806).
  `ffu --connect ... --still` takes no pilot, so those parts never show; `--connect ... --name pilot --hud --clip
  out.mp4 --seconds 5` flies one, and its last frame is the still. The clip is x264 4:2:0 at crf 18 (`ffmpeg()` in
  `crates/ffu-client/src/main.rs`), which smears 1 px edge detail such as icon specks. For pixel evidence put an
  `ffmpeg` shim first on PATH that swaps `libx264`/`yuv420p`/`-crf N` for `ffv1`/`rgba` and `.mp4` for `.mkv`, then
  take the last frame with `ffmpeg -sseof -0.2 -i x.mkv -frames:v 1 -update 1 x.png`.
- **A before/after pair joins both client binaries to one server at once** (w4260): sequential runs land on different
  ticks (147 against 182), and a critic graded world objects that moved between them BROKEN. Each client's ship
  colour is its player's (`ffu-client/src/ship.rs` `color`, by id), so give each its own `--name` and expect that.
- **Item icons are a premultiplied, padded, mipped atlas** (w4260, `render.rs` `icon_levels`, `ui.wgsl` kind 6). FF1's
  icons carry a pure-white fringe at low alpha (436 of the Bat's 460 edge pixels); filtered as straight alpha at one
  mip level it showed as white specks at 25 px. Keep any new texture with soft edges premultiplied in linear light,
  and judge an icon change at 8x against an area-filtered downscale of its source on the card colour.

## A theme's alpha blends in linear light

The `ui.*` keys of a look file (w4040, ffu #729) restyle every panel through `Theme` without moving it. ffu-ui blends
in linear light on an sRGB target, so a theme alpha a shows about as much of what is under it as a CSS alpha of
a^(1/2.2) would in a browser mock: a panel at 235 of 255 still showed the world at about 28 % of its brightness, and at
B's 189 the models crossed the inspector's text (measured). Convert a mock's CSS alphas (an edge line 0.55 is about
0.55^2.2 = 69 of 255), measure the show-through on a still over the world, and keep a button opaque: a focus fill of
accent-over-alpha came out darker than an unfocused button (UI critic round 2).

## Focus: an accent outline and corner brackets, in a gap the row leaves

Since w4105 (ffu #776, r197's style B) a shaped control has an outline primitive: the focused button's outline is
`ui.accent` (`Theme::outline`, `Shape::Focus`) and `render.rs`'s `focus_marks` draws four corner brackets
`BRACKET_OUT` (5 px) outside it. Never grow the control or add a second ring on focus: critic round 1 read a 116 px
button that became 126 px with a ring as "grown into its neighbour". Leave the brackets room: the button row has a
10 px gap and 6 px left and right padding, so a bracket stands in the gap and inside the panel's content edge. Tiles
keep their own fill under focus (a closed slot stays dark, FP.21, w2895).

## Matching a mock, measured (w4105, three ui-critic rounds)

Measure each of these on the still beside the mock before a critic round; each one was a critic's UGLY:
- **Get the mock pictures attached before you start**: r197's and r215's stills live behind the portal's login
  (`/srv/fff/review/w4014-ffu-art-direction/picked-panels-full-{1080,deck}.png`, `.../w4105-ffu-style-b-panels-v6/`),
  and `docs/ui-style/ref/*.png` in a checkout can be 26-byte login errors. w4105 and w4201 both stalled on it, and
  w4201 shipped its glass item as a follow-up: ask your orchestrator in your first report to attach them.
- **Corners are per part** (`Corners` on `Spec`, w4201, ffu #792): `Theme` follows the theme's family, `Square` for
  buttons, close and pager, `CutBottomRight` for every tile. Give every tile in a panel the same one: critic round 1
  graded the Assembler's recipe tile, still cut at both corners beside bottom-right-only input tiles, UGLY.
- **Focus distance, two sources**: r197's spec puts the brackets 7 px out and a 1 px ring 3 px out; w4201's brief asked
  for brackets about 3 px out, joined by the ring. `BRACKET_OUT` 2 (3 device px at 1080) follows the brief. Quote
  both when they disagree, and build what the person's latest words say.
- **A still of the ship's Hold**: serve the snap (`ffu-server --start world.snap --listen 127.0.0.1:P`), then
  `ffu --connect 127.0.0.1:P --name pilot --autoloot --clip hold.mp4 --seconds 25 --size WxH --look looks/ffu.look`,
  last frame with `ffmpeg -sseof -0.1 -i hold.mp4 -frames:v 1 -update 1 hold.png`.
- **Tile icon size**: the art inside an icon cell has a transparent margin, so the box must be bigger than the art you
  want. FF1's sprites fill about 74 % of their cell; at 0.8 of a 5 px-inset square the art filled 47 % of a 60 px tile
  against the mock's 63-65 %. Now 0.95 of a 3 px inset (`render.rs` `TILE_ICON`, `frame.rs` `TILE_INSET`), top left,
  about 62 %, the count on the icon's corner with a halo on all eight sides.
- **Title on one line**: a heading shrinks to one line while that keeps three quarters of its size, and wraps only
  past that (`lib.rs` `fit_px`): "SHIP ASSEMBLER #1984" wrapped at tracking 0.14 em; r197's tracking is about 0.1.
- **Title weight**: Khyay's own stroke is about half the mock's; its glyphs are drawn twice, `round(px*0.75)` apart
  (`render.rs` `HEADING_FONT`), as FF1's TMP widens bold titles.
- **Quiet lines**: outlines are `px.floor()` wide (one device pixel at 1080p and under); `ui.slot_edge` alpha 36 gives
  r197's 27, 80, 110 over the glass. Rounded widths drew 2 px lines at 1.4x the mock's brightness.
- **Text sizes relative to each other**: info rows (Status, Power, Facing) are 12 px under the buttons' 13 px, in a
  2 px-gap column (`inspector::INFO_PX`); at 14 px and the panel's gap they stood 37 px apart against the mock's 20.
- **A fitted text keeps its box height**: taffy's measured width can differ from the rounded box, so a fitted text
  wrapped one line more and spilled 1 px (`tests/bounds.rs`). The shape pass lowers px until the height fits.
- **Layout per mock, not per building class**: a store (Cargo Hold) shows grid, rule and detail row and no Rotate,
  Copy, Remove, because its mock shows none; the critic graded the added row BROKEN under "add no layouts they don't
  show". An empty store still needs a non-empty sub line ("0 in hold"): `tests/gate.rs` fails a label with no text.
- **Bottom room**: 6 px margin under the last button row, so the brackets do not crowd the panel's edge.
- Give the critic the round before as the "before" so it can check that nothing moved.
- **Match a glass colour on the glass alone, never on a whole panel's median** (w4215, three ui-critic rounds): r197's
  panel medians (9,27,43 and 15,31,46) count the slot cells and the lit world showing through, and two tokens aimed at
  them were graded UGLY (slate, then a flat navy). Sample thin strips between slots: the mock's glass is 4,10,18 to
  4,11,22, and its empty slots are 6,17,27. Then FFU's old token was already within about 1 dE00. Over FFU's warm
  belts, a higher alpha (215) keeps the glass from going grey. Measure candidates on the glass between slots, on an
  empty slot and over lit belts, beside the mock, before the critic sees them. pr_evidence's `Pinned:` and
  `Covered text:` need a Unity census that FFU does not make: say "not measured" and why.

## The HUD: matching r197's HUD mocks (w4106, three ui-critic rounds)

- **The HUD has its own scale**: r197 draws the HUD at 1.5x at 1080 lines and 1.2x on the Deck's 800 (measured), not
  the panels' `scale_for` (1.11 at 800). Lay a HUD tree out with `hud_layout` (`hud_scale`), and set a size the mock
  draws differently at 800 with `by_height(height, at_1080, at_800)` (`lib.rs`). Gate HUD panels at that scale
  (`tests/gate.rs` `hud_panels`, `gate_hud`). Measure every text and box at both mock sizes, not only at 1080: the
  chip text, the map's coordinates and the speed card were 10, 8 and 46 px at 800 against the mock's 13, 12 and 36.
- **Taffy resolves a nested absolute node's right and bottom insets against the screen** (measured): only left and
  top insets place an absolute node below the root. Place a slot's key or count with left and top insets, or keep the
  count in normal flow with `justify_content`/`align_items` `FLEX_END`.
  Percent sizes too: a nested absolute row at `percent(1.0)` width came out the screen's width (w4245, ffu #799).
- **Size a bottom-edge HUD row to its card, never the screen's width** (w4245, ffu #799): an absolute row spanning the
  screen is a sibling of every other bottom piece, and the gate failed "hud.station overlaps its sibling hud.abilities"
  once w4196's station card landed. Centre it as left `percent(0.5)`, margin left minus half its width, width the card's.
- **A centred row's fractional left edge rounds its children apart** (w4245): at 1280x800 a tile column rounded to 39
  px while its absolute prompts child of the same logical width rounded to 40, and the gate failed "leaves its
  parent". Make such a child half a logical pixel narrower than its parent.
- **r197's 10 px key prompts cannot hold text at the gate's 9 px floor** (w4245): the ability tray's pills are 12 px
  at 1080 (15 px at 800, as the brief says). Say so in the PR rather than shrinking the text under 9 px.
- **Size an icon to the art the mock draws, not to its square**: FF1's art has a clear margin, so a 25.3 px box drew
  the Connector 28 px wide and a 36 px box drew it 43 px, against r197's 40 (measured). Find the box by measuring the
  drawn art's width (33.5 here).
- **Clear a title on a map with a box around its text**: a band the width of the disc under the title cut the map
  along a straight line, which the critic graded UGLY as a clipped texture. Keep the cells out of the text's box plus a
  margin only (`minimap::title_clear`).
- **The gate's sibling-overlap check exempts an Image and a Value**: a key or count over its item art is meant.
- **Test a HUD card with the longest real figures, not the mock's** (w4196, ffu #802): the Station card's figure
  cells grew from `flex_basis: 0`, so "0 Wh / 1.40 kWh" ran 4 px past the card's edge on a real-client still while
  every test with the mock's figures passed. Lay figures out in columns of cells with `flex_shrink: 0` and width auto
  (`hud.station.left`/`right`), and test long values in every locale at the three sizes
  (`long_station_figures_stay_inside_the_card`). Run clippy as CI does, debug, never `--release`: code under
  `debug_assertions` holds uses, and a release clippy fails on unused items CI never sees.
- **Alert tiles and text over art** (w4246, ffu #807, three ui-critic rounds): text drawn over an item's art gets the
  dark halo only as a child of that `Role::Image` (`render.rs`: a Value whose parent is an Image); `Spec::art` places
  the art inside its box (left, top, side as parts of it). A bold sans is `Spec::bold` (the body face drawn twice, the
  halo under both copies): `title_face` Khyay's footless "1" with a hard halo box was graded UGLY as a prototype font.
  Sample a mock's colour by counting its pixels (`ffmpeg -f rawvideo -pix_fmt rgb24 -` into a Counter), never one
  pixel: a first pick of #F76834 was the art's orange; r197's count is #FF8A7A. An absolute row's box is its whole
  inset span: left 0, right 50% overlapped w4196's station card in the gate's sibling check though no tile did; use
  left auto with a right margin. A heat test world: an Assembler joins an Antimatter Station's grid only when placed
  after it (40 steps) facing its slot, and the station passes 100 near tick 19,782 (ffu-client `alerts.rs` world test).
- **A merge where git interleaves two appended functions**: run `git merge-file --diff-algorithm=patience` on the
  `:1:`/`:2:`/`:3:` stages (`git show :2:<file>`); the conflicts come out as whole blocks to keep both of (w4246).
- **Real-client stills** for a HUD: serve a world with `ffu-server --dir <dir> --start <world.snap> --listen
  127.0.0.1:P` (it needs both `--dir` and a snap: no `combat:` start; save one with `ffu-headless run --start ... --ticks
  1 --save`), then `ffu --connect <addr> --name pilot --hud --minimap --clip out.mp4 --still out.png --seconds 4 --size
  1280x800 --look looks/ffu.look` (without `--minimap` there is no map). Pass `--clip` with `--still`: a connected
  `--still` alone draws as a viewer with no pilot, so the ship's readouts are missing (w4241, ffu `main.rs` connected
  still path). `--clip` needs `ffmpeg` on PATH; biscuit has none, and a static build in `$TMPDIR` works: `UV_CACHE_DIR=$TMPDIR/uvcache ~/.local/bin/uvx --from imageio-ffmpeg python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"` prints its path (w4242). A world in a
  set state (a damaged ship) comes from a small crate in `$TMPDIR` with a path dependency on `ffu-sim` that submits ops,
  steps a `Sector` to the state and writes `snapshot::encode`. An `--autobuild` of an item the ship holds 0 of gives
  the refusal notice for a still.
- **r197's Deck mock (`hud-deck`, a 2x2 of quadrants) hides the top readout row under quadrant B's caption** (w4242,
  ffu #801): a readout's place at 1280x800 cannot be measured there. Derive it (the 1080 offset to the speed text, scaled
  to the Deck's speed text at x 459, w4106) and say "derived, not measured" in the PR and the report. FF1's fleet icon is
  FF1's `Resources/Icons/Bat` sprite, added to the PersonalDisplay in FF1's main scene; in FFU it is `content::BAT`.
- **Trace every card in a mock to its FF1 object before you build it** (w4241, ffu #798): r197's top-left "Hull
  612/700" card is FF1's `TechProgressBar`, research progress (FF1's main scene, line 243408, FF1 TechProgressPanel line 147), and
  FF1's health is a segment of the readouts card (FF1 PersonalInfoDisplay, lines 91-106), which r197 called "construction
  bots". Find the object by its place in FF1's main scene (anchors and position) and the code that sets its text.
- **A card that grows beside a centred fixed-width segment pads unevenly** (w4241, critic UGLY: 10 px left against
  18 px right): beside another segment, give the fixed one its text's width and anchor that text where the lone card
  centred it (`hud.rs` `speed_at`).
- **Measure a title's letter spacing on the word it will show** (w4197, ffu #805): `text::LIGHT_TRACKING` 0.3 em was
  tuned on "MAP". On "HAVEN" it drew 78 px with 6-8 px gaps, against the 1080 mock's 66 px and 3-4 px; 0.15 em gives
  68 px with gaps 4/3/4/4 (a per-column ink scan of both stills).
- **Cut the own ship's marker to the map's box, not the sector's rectangle** (w4197): clipped to `Fit::area`, a ship
  near the sector's edge lost half its ring on the Deck still. `ships()` now clips it to `Fit::view`;
  `the_own_marker_is_whole_at_the_sectors_edge` failed before and passes after.
- **Crop the quadrant of the style you build from a multi-style sheet** (w4197): r197's `hud-deck.png` holds styles A
  to D. Style B is the bottom-left quadrant (x 0-964, y 604-1208, scaled 1.328 to 1280x800). A critic round graded the
  pack BROKEN because the 800 comparison used style C.
- FF1's hotbar defaults are `GameInitializer.StartHotbarItems` in FF1's main scene.
- The Write and Edit tools may refuse to create a file in an ffu slot (w4106, m5): write it in `$TMPDIR` and copy it
  in, and edit with a small Python script that checks each replacement's count.

## A pick's answer and other HUD motion (w4107, ffu pick feedback a)

- **A local `--pick X,Y` clip runs as a pilot only with `--name N`** (ffu `main.rs`): without it the ship holds
  nothing and the "N in hold" note never shows. `ffu --start world.snap --name pilot --hud --pick X,Y --view X,Y,48
  --clip out.mp4 --seconds 3 --size 1920x1080 --look looks/ffu.look` records 60 fps and picks at frame 60.
- **A clip loop must age what the window ages**: the local clip never called `Builder::frame`, so the pulse ring sat
  at its first frame for the whole clip while the stills looked right. Check motion on a frame strip, never on stills:
  `ffmpeg -i clip.mp4 -vf "select='between(n,56,87)',crop=W:H:X:Y,scale=iw*2:-1,tile=8x4" -frames:v 1 strip.png`
  (m5's ffmpeg has no `drawtext` and refuses `-vsync`; read frames left to right from the first). watch_video's vfx
  detector anchored on the pointer's move, not on a 6 px ring.
- **Turn a tile into screen pixels through the tilted look camera** (`Camera::to_screen`): a flat-camera `tile_pixel`
  picked a Belt beside the Assembler it aimed at.
- **Tell the critic what each part of a mock is**: the first critic round graded every still BROKEN for a "missing hand
  chip" because it read r197's dashed ghost tile at the cursor as the chip, and for a note "beside the ghost". Quote
  the design's own words in the brief and name the parts (ghost, chip, note, slot); the second round then judged the
  real differences.
- **A frame a shared token draws goes on its own node**: the hotbar's selected slot and w4105's focused hold tile share
  `TILE_FOCUS` (`Shape::Pick`, 1 px outline). The mock's 2 px hotbar frame is a `hud.selected` ring, so the hold grid
  keeps its edge. The gate's sibling-overlap check exempts `hud.pulse` and `hud.selected` by name.
- **Measure a line's width; don't take a critic's word for it**: round 1 called the selected slot's 1 px edge too thin
  against a 2 px mock, round 2 called the 3 px fix too thick against a "1 px" mock. One pixel row through both settled
  it (mock 2 px at the still's scale, checked by the slot's width): `ffmpeg -i still.png -vf
  "crop=20:1:X:Y,format=gray" -f rawvideo - | od -An -tu1 -v`. A width in logical pixels is times the HUD's scale (1.5
  at 1080): `RING_WIDTH` 4/3 draws 2.
