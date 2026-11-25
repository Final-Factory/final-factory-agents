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

- **Check a "FF1 draws no X" claim in FF1's presentation code and a real-game still before you write it** (w5484,
  lothsahn: "Power distributers show a link in FF1 when powered.  Why do you say there's no link?"). The Power
  Distributor aim design said FF1 draws no line between linked distributors, from a search summary; FF1 draws a teal
  beam through `ScalableLaserOwner` (`PowerTransmitterBehaviorSystem.cs:160-203`, `ScalableLaserPresentationSystem.cs:187`),
  only while power flows. Grep the presentation side (`ScalableLaser*`, `*LinkSystem`, `*Highlight*`) and the
  building's config for a WeaponConfig or effect prefab, and look at a still of the real game in the state the claim
  is about (powered, unpowered, ghost), before any negative claim about FF1.

- **Draw a new panel's mocks over the person's picked HUD, and list what they drop from FF1, before the pick** (w4299,
  the Hauler route panel). Round 1 sat on a plain background, and ben's orchestrator sent it back: "shoot each mock over
  the real FFU HUD from r197's picked HUD mock", and list every FF1 control the panel drops "with why" and the row that
  adds it. Over the real HUD, measure where the window sits against Objectives, the hotbar and its label, and the
  Station card, at 1920x1080 and 1280x800. Give the fresh ui-critic that HUD still as its reference (`ui_look.py pack
  --ref`). r197's stills are behind the portal's login: ask the orchestrator to attach them.

- **A still of an opened panel from the built client** (w2895, ffu #652): `ffu --start world.snap --still out.png
  --inspect X,Y --press A,B` opens the inspector of the building at X,Y and presses the named nodes in order before
  the still. The FF1 world: `ffu-headless ff1 import tools/world/ff1-trailer-staging-0.50.0.54.zip`.
- **Aim FF1-world stills and clips at its base, not its centre** (w4852, w4853). The centre (1291,1248) is empty space.
  The base is at about `--view 820,1680,10`; at zoom 10 the whole base fits, and at 56 each connector's chevrons can be
  read. `--connect ... --still` takes no pilot, adds no ship ("0 new owners") and fits the whole sector. A clip that
  places on the FF1 world needs a free-build import (`ff1 import <zip> --free-build`): on the charging world a new
  pilot's ship holds nothing, so every place is refused ("the ship holds no connector"). `--autodrag N:FACING` (w4853)
  holds that rotation during the drag.
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
- **A connected still set needs a fresh `ffu-server` for every shot** (w4866, ffu #903). The client's `--autoloot` loots
  the start wreck once. With one server shared across 14 shots, only the first client opened the Hold, and the later
  shots' edit steps (`--hotbar-edit`) never fired. Their stills looked plausible and showed nothing. Start a server per
  shot on its own port (`47800+n`, each under `timeout`). Check each client log for every step it fired before you
  grade a still. A step clip must also run until its last step has played, not a fixed 2 s after the loot.
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
- **One corner shape across a window** (w4345, ffu #847): a fill in a colour of its own is `Shape::Plain`, which drew
  `CutBottomRight` square beside cut token fills until #847 (render.rs). Small-shape token fills (BAR_BACK, BUTTON,
  FIELD_FILL, CURRENT) carry `ui.slot_edge`'s 1 px outline; an unoutlined row takes a colour of its own. Match the mock's
  corners on every control: mixed square and cut was UGLY (Ben, w1761: "differing border-radius values all smashed together").
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
- **The alert row wraps at 4 a line; lift grey art on its fill, never dim it** (w4264, ffu #810, three ui-critic
  rounds). Five tiles in one line overlapped `hud.station` at 1280x800 in `tests/gate.rs`. `hud.rs` `ALERT_COLUMNS` is
  4 (FF1's AttackWarnings grid), and the extra tiles go on lines above, right-aligned, so the bottom line never moves
  (`hud.alerts.line{n}`). The hotbar's dimmed `GREY_ICON` on the alert tile's maroon fill measured 1.6:1, which the
  critic graded UGLY. Alert tiles draw grey as luminance lifted 0.2 in linear light (`ui.wgsl` kind 6, `extra.x` 2),
  which measured 5.0:1. Measure grey art's contrast on the fill it sits on before the critic round.
  Merge-on-green's Evidence check (`pr_evidence.py`) counts any `ui.wgsl` edit as an art change. It refuses a PR
  without `Reference capture:` (the real-client still of what the change replaces) and `Art language:` (the two solid
  colours and the HDR accent, or "none") lines: run it on the PR before `blocked_on` (w4264 lost a merge to it).
- **Dim a 0-count tile in its own colours, never grey, when tiers differ only by colour** (w4423, ffu #874). The
  building tabs' 0 tiles first used `Spec::grey` (GREY_ICON with the colour stripped). ui-critic round 3 graded the
  Logistics tab UGLY: FF1's Inserter Bot, Fast and Express (blue, crimson, green) became three identical dark
  silhouettes. `Spec::dim` (render.rs: the GREY_ICON tint with `extra.x` 0, no shader change) keeps each icon's hue at
  about 1/6 to 1/10 of a held tile's brightness. Round 4 graded it OK.
- **Count a tab row's width in the longest locale before you add tabs** (w4423). Two more icon tabs pushed the Crafting
  panel's row past the panel at 1280x800, by 2 px in en and 20 px in pt-BR, and `tests/gate.rs` failed 429 times
  (`craft.tab.build_logistics leaves its parent`). The fix lets the icon tabs shrink only when the row overflows
  (`flex_shrink` 1 and `min_size.width` 20 on the icon tabs, 0 on the text tab). Add every new tab's pages to
  gate.rs's views.
- **Take FFU stills on the FF1 import world, not `scenario::factory`** (w4423, lothsahn: "why in the screenshot does it
  show belts? We don't have belts in FF1."). factory's Belt, Miner, Crafter and Sink are FFU skeleton kinds (w2757)
  with no FF1 equivalent. Use `ffu-headless ff1 import tools/world/ff1-trailer-staging-0.50.0.54.zip --pilot pilot`.
- **A merge where git interleaves two appended functions**: run `git merge-file --diff-algorithm=patience` on the
  `:1:`/`:2:`/`:3:` stages (`git show :2:<file>`); the conflicts come out as whole blocks to keep both of (w4246).
- **A still of an animated HUD part catches one phase: judge the frame you pick from the clip** (w4275, ffu #832).
  The ability tray's hint frame (FF1's `RedAlertFrame` compact look, `ui.wgsl` kind 8) flashes its ring between 1 and
  0.3 twice a sweep. The lossless `--still` caught the 0.3 phase: 67 orange pixels against FF1's 123, which read as a
  frame too thin. Pick the frame from the clip by counting alert-orange pixels in each frame (`ffmpeg -f rawvideo -pix_fmt
  rgb24 -` into a counter). Also show a strip of phases (`-vf "fps=10,crop=...,tile=4x4"`).
- **A connected client's player id comes from its `--name`, not 1** (w4275): `pilot` is 268856033, printed in the
  client's line `ffu: flying pilot (player N)`. No public op gives fleet ships outside a yard, and `restore_fleets` is
  `pub(crate)`. To build a snap that gives that pilot ships, make it `pub` for the snapgen build only, then revert it.
  The ui-critic graded a hint frame on a tile with no ships (a greyed 0/4) UGLY, so give the world the ships the step
  uses.
- **Real-client stills** for a HUD: serve a world with `ffu-server --dir <dir> --start <world.snap> --listen
  127.0.0.1:P` (it needs both `--dir` and a snap: no `combat:` start; save one with `ffu-headless run --start ... --ticks
  1 --save`), then `ffu --connect <addr> --name pilot --hud --minimap --clip out.mp4 --still out.png --seconds 4 --size
  1280x800 --look looks/ffu.look` (without `--minimap` there is no map). Pass `--clip` with `--still`: a connected
  `--still` alone draws as a viewer with no pilot, so the ship's readouts are missing (w4241, ffu `main.rs` connected
  still path). `--clip` needs `ffmpeg` on PATH; biscuit has none, and a static build in `$TMPDIR` works: `UV_CACHE_DIR=$TMPDIR/uvcache ~/.local/bin/uvx --from imageio-ffmpeg python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"` prints its path (w4242). A world in a
  set state (a damaged ship) comes from a small crate in `$TMPDIR` with a path dependency on `ffu-sim` that submits ops,
  steps a `Sector` to the state and writes `snapshot::encode`. An `--autobuild` of an item the ship holds 0 of gives
  the refusal notice for a still.
- **A hauler panel over the FF1 world** (w4345, ffu #847): `ffu-headless ff1 import <zip> --out world.snap` (no
  `--out` only prints JSON), serve it as above, then `ffu --connect ... --name pilot --hud --minimap --hauler h.snap
  --route --clip x.mp4 --still x.png` (`--hauler` connected needs `--clip`; the camera follows the pilot). An offscreen
  `--start` still over the big world was blank. macOS has no `timeout`: `perl -e 'alarm shift; exec @ARGV' N cmd`.
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
- **A HUD card's cut corner needs `ui.card_cut`** (w4243, ffu #800): `Corners::CutBottomRight` on a `Shape::Card` drew
  square, since the Card shape's cut was 0. `Theme::card_cut` (`looks/ffu.look` `ui.card_cut = 4.67`, 7 device px at
  1080, measured on r197's mock) cuts it; tiles keep their own cut.
- **An arrow node's text is still laid out** (w4243): a footer or toggle button drawn as a triangle (`Spec.arrow`)
  keeps its text as the layout and accessible name, and a word there failed the gate's "leaves its parent" check. Give
  it one glyph (`‹`, `›`, `v`); a separate accessible name is a follow-up.
- **A glyph the font lacks is a drawn `Symbol`** (w4345, ffu #847): Roboto has ↓ ↑ × › ‹ but no → ← or chevrons
  (fontTools). Draw a bar grid, 1 device px per cell; a cell never shrinks under 1 px (`Symbol::place`), so size the
  box `cols/1.5` at 1080 and `cols/1.2` at 800 (HUD scales) or the gate fails it, and keep grids 9+ columns for 9 px.
- **Read the PR's state just before you push a fix onto another worker's branch** (w4317): a critic fix pushed as
  cf0c384c landed on #828's branch about a minute after #828 merged. The push succeeded, but onto a dead branch, so
  the fix had to move to follow-up #830. Run `gh pr view <n> --json state,mergedAt` right before the push. If the PR
  merged, branch from `origin/main`, cherry-pick, and open a follow-up PR.
- **A stills script builds nothing: build first** (w4243): a script that runs `ffu-server` and `ffu` from
  `$CARGO_TARGET_DIR/release` drew the last build's client, and a critic round graded an old card. Run `cargo build
  --release -p ffu-server -p ffu-client` before every stills leg.
- **`pr_evidence.py` reads `Reference capture:` and `Art language:` only as plain labels** (w4243): bolded
  (`**Reference capture:**`) it still failed. A `ui.wgsl` change in an ffu PR asks for both: name the mock still as the
  reference and the HUD's two colours and its one accent.
- **pr_evidence's Unity-census lines** (Overlaps, Moved, Pinned, Style delta E, Critic pack id, Window overlaps) have no
  ffu source (w4345): write each "not measured (no Unity census)" with the stand-in, `crates/ffu-ui/tests/gate.rs` and a
  layout test that opening the panel moves no other HUD node.
- FF1's hotbar defaults are `GameInitializer.StartHotbarItems` in FF1's main scene.
- **Check an ffu PR's Evidence with `pr_evidence.py --repo Final-Factory/ffu --pr N`, after `gh pr create`** (w4302, ffu
  #857): a local `--body-file` run, with `--repo` and `--files-file` too, applied the game repo's rules to
  `crates/ffu-ui` and asked for `Kind:`, a claims table and `Not verified:`; the `--pr` run on the same body answered
  "PASS: no game code or assets changed" (as for #810 and #849). Fix the body with `gh api -X PATCH repos/Final-Factory/ffu/pulls/<n> -F body=@<file>` if it fails
  (`gh pr edit` exits 1 there on the Projects (classic) deprecation).
- **The Landing Zone has no build-menu entry** (w4302): `inspector::kind_item(Kind::LandingZone, ..)` returns `None`,
  so an alert tile or card for it names `ffu_sim::content::LANDING_ZONE` directly.
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
- **Key prompts are tabs cut like their tiles, in a row clear above them** (w4280, ffu #829, three ui-critic rounds):
  a round key chip (`Shape::Key`, round ends) on or beside the ability tray's cut-corner tiles was graded UGLY in
  rounds 1 and 2 under Ben's w1761 words ("i dont like the differing border-radius values all smashed together"),
  first overlapping the tile's corner, then 3 px above it. Draw a prompt as `Corners::Fine` on a `Shape::Key`
  (`render.rs` `KEY_CUT`, cut at the tiles' two corners) in a row `PROMPT_GAP` (4 logical, 6 px at 1080) above the
  tile (`hud.rs` `tray_tile`); round 3 found 0 BROKEN or UGLY. One corner family per row: check every small part
  (key, count, badge) against the tile it sits on before the critic round.

## A full screen: the research picker (w4367, ffu #864)

- **Played checks with no server**: `crates/ffu-ui/examples/research.rs` writes its scenes as snaps
  (`research-{early,mid}.snap`), and `ffu --start <snap> --still|--clip out --research --press research.add,...`
  presses T, clicks each named node where the screen lays it out, steps one tick per op and prints the sim's queue as
  JSON. A local `--clip` drew only the `--inspect` panel before w4367: a new screen needs its own branch in the clip
  loop, and `scene.builder.frame(..)` called each frame, or its hint frame never crawls.
- **FF1's early tree is one chain**: a new sector has one Available tech, and skipped objectives pay research into the
  pool, so "Research now" on the hinted tech can finish it at once; assert active or unlocked.
- **A pager past 12 pages ran its dots out of the panel**: `frame::MAX_DOTS` (12) drops the rest; the gate caught it on
  the Locked tab (26 pages).
- **A screen that runs over the hotbar at 800 lines hides the HUD while open** (FF1's tech tree is modal), rather than
  shrinking the page size the person picked (Ben: "Use A, the single column with 6 techs a page").
- **The detail shows a tech of the open tab**: the critic graded a Locked tab whose detail kept the hinted Available
  tech UGLY; fall back to the shown page's first row (`research.rs` `shown`).

## Dropdown lists in a window (w4397, ffu #875, three ui-critic rounds)

- **`inspector::highlight()` re-inks the focused node's children** with `BUTTON_FOCUS_TEXT`, not only its fill: a
  focused filter field's placeholder and magnifier went bright, which the critic graded off the mock. Restore their
  colour after highlight (`route.rs` `list()`, the hint at 122, 150, 168).
- **A theme fill token is also a shape** (`theme.rs` `fill`): giving an add button `BUTTON_FOCUS` to show its list is
  open drew the focus brackets on it. Add a distinct token (`frame::BUTTON_OPEN` maps to `Shape::Pick`: the button's
  own fill, the accent ring, no brackets).
- **A list row needs its own focus**: the panels' 5 px brackets on 22 px rows were graded UGLY twice. Rows take
  `Shape::Row` (`frame::ROW_FOCUS`: the chosen row's blue, a 1 px accent outline, thin brackets 2 logical px off,
  `render.rs` `ROW_BRACKET_*`) and `Corners::Square`, since a cut corner clashed with the brackets.
- **Keep focus inside an open list** with `Spec::modal()`: every other control gets `Node::inert`, and `UiTree::hit`
  and the arrow graph skip it.
- **Rebuild the release client before every critic round**: a stills script that only runs the binary shot the old
  build, and a round was spent grading stale stills.
