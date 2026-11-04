Request: w2895

R.S1, the dark-mode nebula skybox. FFU now has its own sky in place of FF1's six `Nebula_Mesa_4K_*DARK` faces. No pack face is brought over. **Held for Ben's look; do not merge before his OK.**

## What

- `ffu-bake darksky OUT.ffpack [SIZE] [--faces DIR]` (`crates/ffu-bake/src/darksky.rs`) bakes the R.T5 portal's procedural sky all the way round. It uses a dark look: deeper blues, half the faint stars in clumps, and a magenta knot with a hotter core. A fixed rotation (`TURN`, plain literals, no sin or cos) keeps the default straight-down view mostly dark, with colour at its right edge as FF1's has. The bake makes six 2048 faces and their mips as the `sky:dark` record.
- `surfaces::sky` becomes `sky_with(d, &Look)`. `PORTAL` holds today's constants, so the accepted portal face stays byte-identical (`committed_surfaces_match_the_generator` passes).
- `ffu --pack DIR` now draws the first sky in DIR behind the sector (`packs::sky_in_dir`, `Scene::with_sky`, `QuadRenderer::set_clear(false)`), in both the window and offscreen stills. `--sky-view x,y,z[,fov]` aims it.
- Docs: the PLAN.md R.S1 row and pack-recreation.md R.S1 now say how it was done.

## Evidence

- Reference capture: FF1's own six dark faces were baked into a comparison pack in a temp folder (never committed), and both skies were rendered by the same `ffu` at 9 directions: both poles, a side edge, a side-top edge, a three-face corner, north, west-low, south-low, plus the default view with the sector. Sheets: `/srv/fff/review/w2895-rs1-darksky/sheetA.png` and `sheetB.png`. Default view: `ours_sector.png` against `ff1_sector.png`.
- Art language: two main colours (indigo haze, royal-blue ridges) over near-black, with one bright, bloomy accent (the knot's peach-white core in magenta gas). This is Ben's two-colours-plus-one-HDR-accent rule. It is built additively over near-black, per the R.T5 lessons (`art/surfaces/README.md`).
- No seam: `darksky::tests::the_faces_meet_with_no_seam` checks all 12 cube edges at 128. The texel difference across an edge must stay within 1.5 times the difference inside a face, plus 1. In the stills I found no seam or pinch at the poles, edges or corner (looked). A fresh critic also found none with the stills brightened about 6x.
- Brightness, MEASURED on 1280x720 stills (mean, median and 99.5th percentile of luminance, 0-255):

| view | FFU | FF1 |
|---|---|---|
| default (`pole_down`) | 13.8 / 8.7 / 74 | 12.2 / 6.7 / 70 |
| default with the sector | 26.0 / 11.7 / 112 | 24.8 / 8.3 / 112 |
| north | 11.9 / 9.7 / 39 | 22.8 / 14.7 / 136 |
| south_low | 17.3 / 11.3 / 83 | 45.3 / 36.7 / 171 |

  So the default view matches FF1's, and the side views are darker ("darker, more space, less nebula", Ben on R.T5).
- Bake cost: 36.2 s for 2048 faces on the M5 (release build, MEASURED); the pack is 15.2 MB.
- Critique: three fresh critics ran. v1 was MINOR and v2 MAJOR (the knot filled the default view). Both were fixed. v3 was MINOR with nothing broken, and its first fix (dim the blue ridges so the sky stays darker than the belts) is in this PR. Its other two (move the violet off the factory's purple; a more saturated accent core) are left for Ben's look.
- Local checks: `cargo fmt --check`, `check_sim_rules.sh`, workspace clippy `-D warnings`, `cargo check -p ffu-bake --no-default-features`, and the tests of ffu-bake, ffu-client and ffu-render all pass. No sim code changed.

## Not yet

- FF1's sky turns slowly (`Rotator` on its skybox camera); FFU's stands still.
- That FF1's north is Unity's +Z is a guess. It only decides where the colour sits.
- The F12 screenshot, `frame_bench` and `--capture-check` draw no sky.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

