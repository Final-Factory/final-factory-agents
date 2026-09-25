---
name: timed-out-execute-code-can-run-again
description: "A bridge execute_code call that times out ('Timeout receiving Unity response' / 'Connection closed before reading expected bytes') can still finish AND run again, so side effects repeat: a rig meant to spawn 300 beam owners left ~1,070, which looked like a visual bug until counted. Keep calls short and idempotent, and re-count world state after any timeout. Also: a Step() pump the game re-throttles with vSync, and the overlay-camera setup that procedural draws land in."
---

# A timed-out `execute_code` can run again (2026-09-25, BEAST sandbox, beam VFX)

**What happened.** When an `execute_code` call timed out on the bridge, the editor still ran it,
and the call ran again. The side effects added up:

- A rig that should have spawned 300 mining/research beam owners left **1,069** in the world. A
  screenshot showed a white bloom blob around the asteroid, which looked like a legibility failure
  in the new shader until the owners were counted (`EntityQuery` over `ScalableLaserOwner`).
- Frame-capture loops ran out of order: `f0025.png` had a later mtime than `f0069.png`, because a
  retried "toggle off, capture 25-41" call overwrote frames after the "toggle on, capture 42-69"
  call had finished.
- A retried `Toggle(false)` left the beams switched off after the sequence that turned them back on.

**How to apply.**
- Keep each call short: under ~5 s and ≤ 100 `Step()`s (the ~40 s / 300-Step ceiling in
  [[pumped-execute-code-scripts-can-wedge-the-editor]] is the wedge limit, not a safe budget).
- Make side-effecting calls idempotent: clear, then spawn, in the same call; or check a count first.
- After ANY timeout, wait for the editor (`wait_for_unity ready`, then a trivial `return
  Time.frameCount`), then re-count the world state you depend on before trusting any result.

**Two related traps from the same session.**
- A wall-clock pump loop (`while (sw.ElapsedMilliseconds < 7000) Step();`) on the title screen ran
  ~3,300 frames in one call and backed the editor up for minutes afterwards. Loop on a Step COUNT.
  The game also sets `QualitySettings.vSyncCount = 1` ("Capping FPS to 60") on boot and on game
  start, so set it back to 0 before each pump.
- In play, the world draws through an **overlay** camera named `Main Camera`, stacked on a
  `SkyboxCamera` base (near plane 10000); `Camera.main` returned null in that session, so find the
  camera by name. `Graphics.RenderPrimitives` on layer 0 draws only in that overlay camera, and both
  `ZTest LEqual` and `_CameraDepthTexture` work there (`Assets/Art/Shaders/Vfx/VfxBeam.shader`
  relies on both).
