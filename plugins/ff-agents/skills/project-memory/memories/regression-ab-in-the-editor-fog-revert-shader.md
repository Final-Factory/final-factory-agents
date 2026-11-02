---
name: regression-ab-in-the-editor-fog-revert-shader
description: "Recipes for an editor A/B in a nightly regression check: a fog-targeting fight must sit outside Haven's 950-unit always-in-sight disc; a revert patch must carry the PR's own tests; open main.unity before play mode; an offline shader A/B renders with a CommandBuffer (DrawMesh with a camera plus SubmitRenderRequest draws nothing) and compares a half-float target by relative error ≤ 2^-10, with a mutant control."
---

# An editor A/B for a regression check: fog fights, revert patches, offline shader renders (2026-11-02, w2877)

w2877 (the nightly merge review's regression check of #2997 comets, #2989 fog-edge targeting, #2981 action recorder and
#2398 Plasma Bolt shader, on m3) ran revert-patch A/Bs in a sandbox editor. Each trap below cost a rerun. The scripts are
in the game repo at `specs/regress-2026-11-02-comets-targeting/ab/`.

1. **A fog-targeting A/B needs its fight outside Haven.** `FogSightLock` always counts Haven's disc as in sight:
   `HavenReach` = 90 tiles × 10 + 50 = 950 units round the origin. w1679's fight
   (`specs/w1679-enemies-combat-regress/ab/fight-cmds.txt`) sits within 30 tiles of the origin, so it cannot meet fog.
   Its HEAD and `b4a3069430^1` arms were byte-identical, with 69 acquisitions all in sight, which proves nothing about
   fog. Move the player first with `ffauto:player.setposition|150|0` (a tile: 1500 units out), then place the camps
   with `@dx,dz` offsets around the player. The player's own sight reach measured 244 units. Log each acquisition's
   margin: the centre's distance outside the nearest disc. A ship's body radius is `FogSightLock.DefaultBodyRadius` = 20,
   so an edge acquisition has a margin between 0 and 20.
2. **A revert patch carries the PR's own tests.** `git diff m^1 m -- <code files>` reverted
   `CometCatcherFlightTest`'s targets but not the test, which still named `FinishDivePoopX`. The test assembly failed
   to compile and blocked the domain reload, so the editor kept running the old assembly. Put the PR's test files in
   the diff. After `git apply`, force a compile and confirm by reflection that a symbol the revert removes is gone
   before any arm runs.
3. **Open `Assets/Scenes/main.unity` before entering play mode.** A sandbox editor started with no scene plays an empty
   untitled scene, and the game never starts (heartbeat stays 0). `EditorSceneManager.OpenScene` it once.
4. **Offline shader A/B: use a CommandBuffer.** Under URP in the editor, `Graphics.DrawMesh(..., camera)` followed by
   `RenderPipeline.SubmitRenderRequest` (or `camera.Render()`) drew nothing: 0 lit pixels in every case. What works:
   - Build a `CommandBuffer`: `SetRenderTarget(rt)`, `ClearRenderTarget`,
     `SetViewProjectionMatrices(view, GL.GetGPUProjectionMatrix(proj, true))`,
     `SetGlobalVector("_WorldSpaceCameraPos", camPos)` (billboard shaders read it), and `DrawMesh(mesh, matrix, mat, 0, 0, mpb)`.
   - Run it with `Graphics.ExecuteCommandBuffer`, then `ReadPixels`.
   - Set a global time such as `_FFVfxTime` per frame, to render a 60 fps sequence.
   - Import the old shader under a temporary name beside the new one so its relative `#include` resolves. Delete it with
     `AssetDatabase.DeleteAsset` (the bridge needs `--no-safety-checks`).
5. **Judge a half-float render by its relative error.** A recompiled shader that is algebraically identical still
   differs in a few pixels, up to 122 of 4.4 M, by one rounding step. On an `ARGBHalf` target, a pixel whose
   |a−b| / max(|a|,|b|) ≤ 2⁻¹⁰ (0.000977) is the same pixel. Always add a mutant case that must differ (here the new
   inputs turned on, which reached a relative error of 0.9995). Without one, a render that draws nothing passes as
   "identical".
