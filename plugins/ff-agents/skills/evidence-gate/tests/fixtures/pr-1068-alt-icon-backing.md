<!--
Fixture for test_pr_evidence.py (w438).

FinalFactory #1068, "w410: Alt view icons get a dark backing and shrink at far zoom; every hold shows
its main item", merged 2026-10-05 05:59 UTC, its Evidence section as written (the rest of the description is left out). It passed pr_evidence.py: a full visual
Evidence section, built players, clips, a look. It changed the sprite shader 25 materials share
(scripts/asset_usage.py on its tree) and looked only at the Alt-view icons, so every range ring in
0.50.0.77 filled with a 75% black square (w435, #1076).
-->


**TL;DR:** Alt-view item icons now sit on a soft black rounded plate, so they read on bright, glowing buildings. At max zoom-out they're half their default on-screen size instead of three quarters, which clears the clutter Ben pointed out. Every cargo hold shows the item it holds most of, and an empty hold still shows nothing. No measurable frame-time cost.

## Evidence

Kind: visual

| Claim | Basis | Where |
|---|---|---|
| Icons on bright, glowing buildings now stand out (the "hard to see" fix) | MEASURED: built players, same base and view; 3× crops of the map close-up and zoom 120/250, opacity .6/.75/.9 vs develop. At .75 the icon sits on a dark plate where the develop icon washes into the glow | K_zoom.jpg, 1080_map2.5_before_after.jpg |
| The backing doesn't bury the factory | MEASURED: share of screen pixels Alt view changes (luminance Δ>25, HUD masked): zoom 250 develop 3.6% → 4.4%; zoom 1000 develop 7.8% → 6.1%. Looked at the 1080 and 800 pairs: belts and buildings still read around every plate | 1080_z250_before_after.jpg, 800_z250_before_after.jpg, diff3.png |
| At max zoom icons are clearly smaller | MEASURED: `ScaleFor` unit test (on-screen size at 1000 = 0.5× the default, was 0.75×); looked at the 1080/800 z1000 pairs and clip frames 13–20 s | 1080_z1000_before_after.jpg, clip_frames_before_after.jpg |
| Default-zoom size unchanged | MEASURED: `ScaleFor(250) == 1` (test); z250 pairs | ActiveItemIconScaleTest |
| Cargo holds show their contents; an empty hold shows none | MEASURED: built player, holds at tiles (-67,-11),(-63,-11),(-58,-11),(-54,-11) read via `/v1/snapshot/structure`: AI Controller Circuit, Low Density Structure, Solid State Laser icons; the empty one has none | holds_row.png |
| A mixed hold shows its most plentiful item, without flicker | MEASURED: `CargoHoldAltViewIconTest` (8 cases incl. totals over slots, ties, 2× hysteresis) | Assets/Tests/UI/CargoHoldAltViewIconTest.cs |
| No simulation state changes | SOURCED: `ActiveItemDisplay` is not `[Save]` and no Serialization/FFNetcode code references it (grep of `Assets/Scripts`); its only other readers are `ConstructionBotTaskSystem.FinishConstruction:264-268` (clears it), `RotateInPlaceControllerSystem:372` (re-poses the icon) and `BlueprintTool:531`, and none branch on the shown item. The new code reads inventories read-only (`BufferLookup`/`ComponentLookup(true)`) and writes only the display and its icon entities | Assets/Scripts/FFSystems/Indicators/ActiveItemDisplaySystem.cs |
| No measurable frame-time cost | MEASURED: both builds side by side, 1280×720, vsync off, 8 phases of 20 s (Alt off/on × zoom 250/1000 × 2). Mean frame time differs by ≤0.2 ms per phase (e.g. Alt on at 1000: 16.57 vs 16.53, 13.62 vs 13.44 ms); the same build varies ~2 ms between repeats | perf_ab.json |

Intended look (Ben): "those item icons can be hard to see, factorio has like a blackish background behind them ... make sure it doesnt interfere with the readability of the factory at all" and "at max zoom the alt mode icons are too big, they clutter up the screen"
Built player: yes, Windows dev players from the slot pool: develop 179fb09e1 (before) and a351edb47 (after; the squashed commit differs only in comments and docs), lifeAttackTestSave, 1920×1080 and 1280×800
Clips: w410_before.mp4, w410_after.mp4 (game's own frames, 60 fps container, captured at 37/39 fps): Alt on 0–1 s, off ~1–2.5 s, on again; close zoom ~5.5–7 s; zoom-out 250→1000 ~7–12 s; Alt off/on at max ~14–16 s; map close-up ~17–22 s
Looked: yes, frames at 0.5/2.2/4.0/6.5/13/16.5/20.5 s of both clips (clip_frames_before_after.jpg) and 3× crops of every variant
Review: watch_video --mode vfx on 2× centre crops vs before (watch_video_report.md, watch_video_gemini.md). The blind review says the backing is met ("significantly better" readability) and the max-zoom fix is met. It says holds show no icons; holds_row.png contradicts that (it was looking at the large assemblers, not the 1-tile holds). Its STUTTER/POP flags are the capture rate (37–39 fps into 60 fps) and the instant Alt toggle, which is unchanged from develop.

Tests: FFEditorTests 7598 run, 7582 passed, 0 failed, 16 skipped (pre-existing ignores), on the rebased tree
Save compatibility: none. `ActiveItemDisplay` is not `[Save]`; the two prefabs gain an unsaved component, as the four hold prefabs did in 52991fcb6. SaveLayoutSnapshotTest and GoldenSaveFixtureTests pass.

Not verified: networked storage holds and singularity chests in a built player (the save has none); covered by the shared code path and the query, not seen on screen. The macOS player.

Scheduling: `ActiveItemDisplaySystem` stays in `FFFixedPreTransformGroup` (unchanged); it reads inventories and writes only presentation (the icon entities and `ActiveItemDisplay`, which nothing in the simulation reads). No new per-frame system.
