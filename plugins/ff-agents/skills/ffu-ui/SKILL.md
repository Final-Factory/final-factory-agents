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
design gate, a fresh `ui-critic` agent on the stills, and **move only what the person asked to move**.

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
- New visible text goes into `crates/ffu-ui/src/locale.rs` with every locale's string. A CJK character outside the
  cut fonts means re-cutting them with `tools/subset_cjk_fonts.py`.

## Buttons are ops

A button never writes the sector. `UiTree::hit(x, y)` finds the focusable node under a click, `press` turns it into
ops and `submit` queues them through `Sector::submit` for the next tick, the same path as every other mutation
(`/ff-agents:ffu-add-op`). Rotate is a remove and a place in one tick. Prove a button by its press test: press, one
step, then the sector shows the change.
