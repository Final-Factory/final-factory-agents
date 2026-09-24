---
name: beast-sandbox-editor-driven-from-m5
description: Driving an ffsb sandbox's Unity editor on BEAST from the M5 driver with no worker agent and no Unity MCP — the FMOD CRLF modal-dialog freeze, the pipeline CLI (eval_file, recompile, run_tests), screenshots, and getting commits out without GitHub creds (black hole shader session, 2026-09-23)
metadata:
  type: reference
---

**Freeze trap: "Repair FMOD Libraries" modal.** A sandbox editor whose pipeline calls all time out
(`Main thread operation timed out after 60000ms` in the log) while the process sits at ~0 CPU is
almost certainly blocked by this modal. Cause: the sandbox checkout has `core.autocrlf=true`, so
`Assets/Plugins/FMOD/platforms/mac/lib/**/Contents/Info.plist` and `_CodeSignature/CodeResources`
come out CRLF (`git ls-files --eol` shows `i/lf w/crlf`), and FMOD asks to repair them on every
load, including after each domain reload. Fix it at the source, with the editor stopped:
`git ls-files --eol Assets/Plugins/FMOD | grep 'i/lf.*w/crlf'` → `rm` those files →
`git -c core.autocrlf=false checkout -- <files>` (git diff stays empty) → start the editor.
- Clicking **Ignore** via UI Automation from an interactive scheduled task (`schtasks /it`) does
  NOT work: the sandbox editor runs elevated (`Administrator:` in the title) and UIPI drops the click
  even though `Invoke()` returns normally. Those tasks also flash a console window on Ben's desktop;
  don't use them. A desktop screenshot from such a task is how the dialog was found.
- The ffsb dashboard can report `pid N is no longer this editor` for a live, importing editor;
  check with `Get-CimInstance Win32_Process -Filter "Name='Unity.exe'"` + `-projectPath`.

**Driving it without MCP** (sandbox worker agents lacked Unity MCP; the M5 driver drove it itself):
`C:\Users\rydin\AppData\Local\Unity\bin\unity.exe --no-banner command --project-path F:/ffsb/<name>
--timeout N eval_file F:/ffsb/<name>/Builds/<leg>/x.cs` runs arbitrary C# (`return "...";`). Pass the
path positionally: `file=<path>` is taken literally as the path. scp the `.cs` into `Builds/` first.
Every call has a hard 30 s server-side limit, so keep each eval short and poll.
- Other verbs: `recompile`, `recompile_status` (`{"status":"completed","failed":false,"errors":[]}`),
  `run_tests --mode EditMode --filter FFEditorTests --filter_type assembly --async_tests true` then
  `test_status` (full JSON also in `Temp/pipeline_test_status.json`), `list_tests`.
- `EditorApplication.isPlaying = true` from eval works. Master's editor boots straight into a game on
  play; calling `TitleScreenManager.StartNewGame` on top makes a SECOND `MePlayer` and strands the
  boot at "Generating map…" (`PlayersManager.Me` throws "there are 2").
- Screenshots: focus the GameView, `ScreenCapture.CaptureScreenshot("F:/ffsb/<name>/Builds/<leg>/shot.png")`,
  wait a few seconds, scp it back, crop with `sips`. The sandbox GameView is 3840×2160.
- The editor's fps counter is useless for GPU cost (CPU-bound at 4K). Use
  `PlayerSettings.enableFrameTimingStats = true` + `FrameTimingManager.CaptureFrameTimings()` /
  `GetLatestTimings` for `gpuFrameTime`, and set it back to false (it is a ProjectSettings change).
- Play mode dirties `Assets/Prefabs/Map/MiniMapRenderTexture.renderTexture`; revert it before
  committing.

**Getting the work out** (the sandbox has no GitHub credentials, see
[[feedback-beast-work-goes-through-a-sandbox]]): in the sandbox `git add <files>` then
`git diff --cached --binary > Builds/<leg>/x.patch` (autocrlf-normalised to LF), scp it to M5,
`git apply` in a clean M5 worktree off the target branch, then commit and push from M5.
