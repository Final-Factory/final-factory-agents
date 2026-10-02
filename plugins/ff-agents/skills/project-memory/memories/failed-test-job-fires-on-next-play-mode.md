---
name: failed-test-job-fires-on-next-play-mode
description: An MCP run_tests job that "failed to initialize" stays queued; it fires when play mode is next entered, the boot never reaches the main menu, and the editor is left with no scene open
metadata:
  type: reference
---

# A test job that failed to initialize fires on the next play

2026-10-02, w210, BEAST sandbox. `run_tests` right after a domain reload returned
`Test job failed to initialize (tests did not start within timeout)`: the editor's main thread
was held by the "Repair FMOD Libraries" dialog. A second `run_tests` a minute later ran and
passed. The first request was still queued in the test runner. On the next `manage_editor play`
it fired: the console showed `An unexpected error happened while running tests` and
`InvalidOperationException: This cannot be used during play mode, please use
SceneManager.CreateScene() instead`, `MainMenuPanel` never appeared (frame count in the tens of
thousands, `Updated language` never logged), and after `stop` the active scene path was empty.

Recovery, in this order:

1. `manage_editor stop`.
2. Clear the test state (`TestJobManager.ClearStuckJob` and `TestRunStatus.MarkFinished`, the
   reflection snippet in the drive-game skill, "Compiling and testing around play mode").
3. Reopen the scene: `EditorSceneManager.OpenScene("Assets/Scenes/main.unity", Single)`. Playing
   with no scene open deadlocks the boot (drive-game, Check 1).
4. `play`.

Prevention: after a compile, wait for the bridge to answer a trivial `execute_code` before
`run_tests`, and pass `init_timeout: 120000`.
