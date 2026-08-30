---
name: playmode-needs-main-scene
description: Entering play mode hangs forever unless Assets/Scenes/main.unity is the active scene
metadata: 
  node_type: memory
  type: project
  originSessionId: a4d875de-4479-40ba-86a3-b60d104644e3
  modified: 2026-07-18T23:05:40.705Z
---

Before entering play mode to drive/boot the game, **`Assets/Scenes/main.unity` MUST be the
active scene**. Check `mcpforunity://editor/state` → `editor.active_scene.name == "main"`.

If the active scene is empty (`""`) or anything else, the play-mode boot **deadlocks**: it
freezes in `playmode_transition` (`play_mode.is_changing` stays `true` for many minutes),
stalls right after the log line `ConfigInitializerSystem created`, never builds the
`ItemConfig` singleton, and only `Default World` + `LoadingWorld*` exist (no game world).
`assets.is_updating` stays `false` throughout — a true deadlock, not slow subscene baking, so
waiting does NOT help. It mimics a "wiped-Library subscene" hang; don't misdiagnose — **check
the active scene first**.

**Why:** cost me multiple 6+ minute hung boots before the user pointed out main.unity wasn't
selected. **How to apply:** verify/load `main.unity` before `manage_editor play`; a healthy
boot logs `System Start Controller finished loading...` and `ItemConfig` becomes queryable
across `World.All`. Now also documented in the [[drive-game]] skill's Standard workflow.

**A different-looking symptom, same root cause**: a FRESHLY LAUNCHED editor (via
`launch-editor.sh`, which deliberately deletes `Library/LastSceneManagerSetup.txt` so it boots
with NO scene open) does not hang outright — instead play mode produces an empty ~26-entity
world that LOOKS wedged when stepped via `EditorApplication.Step()` (nothing advances, nothing
errors). Open `main.unity` explicitly before entering play mode on a fresh boot, same as above.
