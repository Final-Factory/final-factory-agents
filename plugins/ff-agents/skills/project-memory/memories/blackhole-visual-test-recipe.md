---
name: blackhole-visual-test-recipe
description: "How to visually test black hole rendering in FinalFactoryMaster2 (save name, teleport coords, gotchas)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 8bfd2a2b-fe60-48c4-97d8-fc78d0f92250
---

To test black hole rendering in-game: enter play mode, then `Serialization.SaveGameManager.LoadGame("BlackHole", true)` via MCP execute_code (user's save with 2 black holes at (-950, 0, 16000) and (13300, 0, 22600)). Teleport the player entity (`FFComponents.Player.Player` + `LocalTransform`) to ~(13720, 40, 22600) — 420 units out.

**Why:** Black holes only exist in deep space; no entity near a fresh spawn.

**How to apply / gotchas:**
- Death radius is 200 units (BlackHoleDeathSystem); ≤250 gets sucked in and killed. Dead player sits at (0, 9999, 0); dismiss the death dialog by invoking the active `RespawnButton` Button.onClick via execute_code (mouse isn't injectable).
- The swirl motion = the rotating skybox nebula (SkyboxCamera's Rotator, ~0.2–0.4°/s, disabled by the "Disable Skybox Motion" accessibility setting) refracted through the lens. The BlackHole.shadergraph Time node is a dead branch — the shader itself never animates.
- The black hole renders on the overlay "Main Camera" (base = SkyboxCamera, stack of 4); Scene Color on overlays needs [[opaque-texture-global-feature]] (Assets/Scripts/Rendering/OpaqueTextureGlobalFeature.cs).
- Game view is pinned to 2560x1440 on this machine and the `FinalFactory/Dev/GameView Free Aspect` menu doesn't exist on MasterUnity60003 — set `UnityEditor.GameView.selectedSizeIndex = 0` by reflection before screenshots, else captures fail/downsize.
- The ItemEntities/BlackHole.prefab mesh is ~600 units across at scale 1 — scaling it up puts the camera inside it (invisible, backface-culled).
