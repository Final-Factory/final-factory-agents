# A batchmode Unity editor never resumes WaitForEndOfFrame in PlayMode

**When:** w1180, 2026-10-18, the game repo's merge-gate smoke test (`PlayModeTests.MergeGate.MergeGateSmokeTest`: title
menu, new game, then a big save). In the windowed editor it passed in 37 s. Under `-batchmode -runTests -testPlatform
playmode`, as CI runs it, the save load never finished: 417 s, no error, the loading screen still saying "Loading player
state...". `SaveGameManager`'s load coroutine ends with `yield return new WaitForEndOfFrame();` before its completion
callback, and a batchmode editor renders no frame, so that coroutine never resumes.

Players do reach the end of a frame, the nightly's `-batchmode -nographics` headless players included: they load saves.
So the fix is scoped to the editor: `yield return Application.isEditor && Application.isBatchMode ? null : new
WaitForEndOfFrame();` (`SaveGameManager.cs`, "A -batchmode EDITOR", PR #1888). The batchmode smoke run then passed in
36 s.

**How to apply:**
- A PlayMode test that passes in the editor's window but times out in a batchmode run (CI, `unity-slot run`): look for a
  `WaitForEndOfFrame` (or `UniTask.WaitForEndOfFrame`) on its path first. `grep -rn WaitForEndOfFrame Assets/Scripts`.
- Guard it with `Application.isEditor && Application.isBatchMode`, never plain `Application.isBatchMode`: that would also
  change the headless players, which work.
- Make a long wait in a test say what it waited on: the smoke test's timeout names the loading screen's text
  (`LoadProgressController.Instance.ProgressText`), which is how this one was found in one run.
