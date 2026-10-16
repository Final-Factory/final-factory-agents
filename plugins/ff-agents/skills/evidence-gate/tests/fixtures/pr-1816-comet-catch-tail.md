**TL;DR:** A comet a Comet Catcher pulls in now looks like a real comet in flight, with finer detail, a subtle sway and a slightly different tail per comet. It turns into a clean cyan-and-magenta swirl over its last ~0.8 s. On the landing frame itself it hits with a hard flash and a spray of debris, then fizzles into the catcher. Ben approved each step on built-player clips (v1 to v5). Presentation only: no simulation, save or netcode change.

Request: w1332

## What changed

- `Assets/Art/Shaders/Vfx/VfxComet.shader`, `Assets/Resources/Vfx/VfxComet.mat`:
  - **Natural tail, more alive** (shared with ambient flyby comets, so every comet stays consistent):
    - fine striations streaming down the dust tail;
    - a faint second strand beside the ion tail;
    - smoother ribbons (dust 14 → 20 segments, ion 8 → 12);
    - a slow sway running down the tail (`Sway`), and a slow breathing of its width;
    - per-comet variety in length, curve, width, sway and tint, from the comet's presentation seed.
  - **Catch look:** over a caught comet's last approach (`_CatchSwirlFrom` 0.15 to `_CatchSwirlTo` 0.55 of the tail's reel-in), it cross-fades into a cyan sheath with two magenta glow lines winding round it, chevrons running up it and a white-hot filament (`CatchSheathColor`, `CatchFilamentColor`, `CatchComaColor`).
  - **Impact and fizzle:**
    - on contact, a hard white-hot flash and 16 hot debris streaks, gone in about 0.2 s (`_CatchImpact`);
    - three arcs crackle at once;
    - fine sparks spiral in, and the core sputters and shrinks into the catcher, over 1.6 s.
  - **No rings or UI-like shapes:** an earlier pass had them, and Ben turned them down.
- `Assets/Scripts/FFSystems/Presentation/CometVfxPresentationSystem.cs` (presentation only):
  - `CometVfxInstance` gains `Caught` (64-byte stride);
  - `FizzleSeconds` is 1.6 (the old splash was 0.7 s);
  - the fizzle clock starts one frame in, so the landing frame draws the impact, not the comet still in flight;
  - `VerticesPerComet` becomes (1 + 20 + 12) * 6.
  - Merged with w1319's comet-cancel blip (#1757) and keeps its logic whole.
- `scripts/feel/run_comet_catch_clip.py`: a comet dive into a catcher in a built player, from the game's own frames (works on a locked desktop). Options:
  - `--dir 1 --zoom 1000` frames the whole tail at the farthest zoom;
  - `--catchers 12 --no-frames` is the cost run.
- `Documentation/Combat-VFX.md`: the catch look, the impact, the preview script and the cost tables.

## Evidence

Kind: visual

| Claim | Basis | Where |
|---|---|---|
| A caught comet is a natural comet in flight and swirls only over its last ~0.8 s | MEASURED: built-player clips, frames stepped; the swirl appears over the last ~0.8 s before landing | /srv/fff/review/w1332-comet-catch-tail-v5/after-1920x1080-far.mp4 (lands ~9.5 s), impact-after-far-10fps.jpg |
| The impact starts on the landing frame | MEASURED: 60 fps frames, frame 7 the rock arriving, frame 8 the flash; watch_video rise 0 frames (master's: 10) | impact-after-60fps-frames.jpg, watch_video-1920x1080-close-report.md |
| The impact hits harder than master's | MEASURED: watch_video strength 10.48 vs 7.47, peak luma 46.6 vs 38.0 (close, 1920x1080) | watch_video-1920x1080-close-report.md |
| No rings or UI-like overlays | MEASURED: every frame of the landing stepped at 60 fps and 20 fps, close and far | impact-after-20fps-1.6s.jpg, impact-after-60fps-frames.jpg |
| No measurable cost with 12 catchers diving at once | MEASURED: 12 catchers, 1280x800, 3 rounds alternated, 26% CPU: frame time at the 60 fps cap in every run, p95 16.69 ms after vs 16.93 ms before; GPU time on the shared GPU too noisy to separate (master 1.9-11.5 ms, new 4.6-6.7 ms) | Documentation/Combat-VFX.md, "Catch look cost" |
| No simulation state changes | SOURCED: the diff touches only the comet shader, its material, the presentation system (PresentationSystemGroup, writes nothing the simulation reads) and a capture script; the per-comet variety uses the presentation seed (`CometTrack.Seed`) | this diff |

Intended look (Ben): "make it look cleaner/more pleasing/more sci fi and also when its coming into a comet catcher, make it fizzle out in a more pleasing, visually interesting way"; then "The vfx should be part of the game world in its appearance"; "i still want it to look like a comet. i do like the swirlig effect right as its about to impact"; "make the texture like higher quality ... randomization to each tail ... more dynamic"; "more oomph and be more immediate upon impact". Approved on v5 (👍 to "Is the impact OK, or what should change?").
Built player: yes (Windows development players from the slot pool, `Editor.ShaderBenchBuild`)
Clips: /srv/fff/review/w1332-comet-catch-tail-v5/before-*.mp4 and after-*.mp4 at 1920x1080 and 1280x800, close (zoom 110, landing ~6 s), wide (300, landing ~6 s), far (1000, whole tail, comet appears ~0.5 s, lands ~9.5 s)
Looked: yes, the landing frame by frame at 60 fps (close) and 10-20 fps (close and far); mid-flight crops before vs after
Review: watch_video --mode vfx on close and far (watch_video-*-report.md); STUTTER flagged on before and after alike (the capture's repeated frames); POP_IN/SNAP at the landing is the requested immediate impact; no blind model review (no Gemini key on lothdesktop)

Tests: FFEditorTests, the 137 classes test_select.py picks: 1362 run, 1352 passed, 4 skipped, 6 failed, all in BlueprintPanelPointerDragTest (NullReferenceException in LocalizationHelper.ApplyLocalizedFont; not in this change; master-batch c8d7bd2354 with this class is green)
Save compatibility: none, no saved state is touched (`CometVfxInstance` is a per-frame GPU buffer)

Real Deck: not verified on a real Deck: the look at 1280x800 was measured on a PC player; how it looks on the Deck's screen and its GPU cost there stay open
Not verified: on a real Steam Deck (see Real Deck)

## Used by

asset-usage: `Assets/Art/Shaders/Vfx/VfxComet.shader` has 1 user (1 material); nothing uses them in turn

| User | Basis |
|---|---|
| `Assets/Resources/Vfx/VfxComet.mat` | TARGET: the comet material this change is for (clips above) |

asset-usage: `Assets/Resources/Vfx/VfxComet.mat` has 1 user (1 script); nothing uses them in turn

| User | Basis |
|---|---|
| `Assets/Scripts/FFSystems/Presentation/CometVfxPresentationSystem.cs` | TARGET: draws every comet with it; caught comets in the clips above, ambient flybys share the natural tail (same shader path as the caught comets' in-flight look in the clips) |

🤖 Generated with [Claude Code](https://claude.com/claude-code)

