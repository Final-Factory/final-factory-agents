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

## The HUD: matching r197's HUD mocks (w4106, three ui-critic rounds)

- **The HUD has its own scale**: r197 draws the HUD at 1.5x at 1080 lines and 1.2x on the Deck's 800 (measured), not
  the panels' `scale_for` (1.11 at 800). Lay a HUD tree out with `hud_layout` (`hud_scale`), and set a size the mock
  draws differently at 800 with `by_height(height, at_1080, at_800)` (`lib.rs`). Gate HUD panels at that scale
  (`tests/gate.rs` `hud_panels`, `gate_hud`). Measure every text and box at both mock sizes, not only at 1080: the
  chip text, the map's coordinates and the speed card were 10, 8 and 46 px at 800 against the mock's 13, 12 and 36.
- **Taffy resolves a nested absolute node's right and bottom insets against the screen** (measured): only left and
  top insets place an absolute node below the root. Place a slot's key or count with left and top insets, or keep the
  count in normal flow with `justify_content`/`align_items` `FLEX_END`.
- **Size an icon to the art the mock draws, not to its square**: FF1's art has a clear margin, so a 25.3 px box drew
  the Connector 28 px wide and a 36 px box drew it 43 px, against r197's 40 (measured). Find the box by measuring the
  drawn art's width (33.5 here).
- **Clear a title on a map with a box around its text**: a band the width of the disc under the title cut the map
  along a straight line, which the critic graded UGLY as a clipped texture. Keep the cells out of the text's box plus a
  margin only (`minimap::title_clear`).
- **The gate's sibling-overlap check exempts an Image and a Value**: a key or count over its item art is meant.
- **Real-client stills** for a HUD: serve a world with `ffu-server --listen`, then `ffu --connect <addr> --name pilot
  --hud --minimap --still out.png --seconds 4 --size 1280x800 --look looks/ffu.look` (without `--minimap` there is no
  map). An `--autobuild` of an item the ship holds 0 of gives the refusal notice for a still.
- FF1's hotbar defaults are `GameInitializer.StartHotbarItems` in FF1's `main.unity`.
- The Write and Edit tools may refuse to create a file in an ffu slot (w4106, m5): write it in `$TMPDIR` and copy it
  in, and edit with a small Python script that checks each replacement's count.
