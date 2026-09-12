---
name: build-after-fast-suite-overwrote-main-scene-and-open-scene-checkout-wedge
description: "A player build scheduled right after the EditMode fast suite wrote the test runner's EMPTY init scene over Assets/Scenes/main.unity (BuildCommand2 saved whatever scene was active; guarded since 80386cea4) — and restoring the file with git checkout while an editor had that scene open wedged BOTH editors (the clone's Assets is the worktree symlink) on the native changed-on-disk modal: shim + bridge time out, ~1% CPU, only a kill + scripts/launch-editor.sh relaunch recovers."
---

# Never build straight after the fast suite; never `git checkout` a scene an editor has open (2026-09-12, 069)

- **What happened.** Unity's EditMode runner leaves its empty init scene ACTIVE. `BuildCommand2` called
  `SaveScene()` unconditionally before the Windows build, and `SaveScene` wrote `SceneManager.GetActiveScene()` to
  `Assets/Scenes/main.unity` — the 7.7 MB main scene became an 8 KB default scene (104 lines kept / 244,717
  deleted), then `SetDemoMode` failed on the missing `DemoController`. The build "failed"; the scene damage was
  silent until the diff.
- **Guard (`80386cea4`, `Assets/Editor/BuildCommand2.cs`):** `EnsureMainSceneActive()` (`:973`, opens `main.unity`
  when a CLEAN foreign scene is active, refuses a dirty one) runs before the pre-build `SaveScene()` (`:232-233`)
  and inside `SetDemoMode` (`:948,955`); `SaveScene()` (`:991`) refuses any active scene whose path is not
  `MainScenePath` (`:964`). Still: after ANY test run, check the active scene before scheduling a build
  (`unity … editor_status` says nothing about scenes — query `SceneManager.GetActiveScene().path` via execute/eval).
- **The second wedge — restoring the file on disk.** `git checkout -- Assets/Scenes/main.unity` while the editor
  (pid 10303) had that scene open left it unresponsive: `~/.local/bin/unity` shim AND the MCP bridge timing out,
  ~1% CPU, no children — the native "scene changed on disk" modal, unreachable with the display off (`screencapture`
  fails, System Events hung). The CLONE editor wedged the same way because `FinalFactory_clone_0/Assets` is a
  symlink to the worktree. Recovery = verify the project path, kill, relaunch via `scripts/launch-editor.sh`
  (new pid boots, compiles, and a still-armed readiness task can reschedule the build on it).
- **Rule:** before touching an open `.unity` on disk (checkout, restore, rsync), close/switch the scene in every
  editor sharing that worktree, or accept that both must be restarted. Same family as
  [[no-external-edits-to-open-unity-scenes]] and [[playmode-needs-main-scene]].
- Related: [[judge-a-build-by-marker-and-children-not-editor-cpu]], [[unity-cli-mpdev-build-recipe]].
