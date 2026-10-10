---
name: linux-worker-first-editor-eula-and-batch-seed
description: First Unity editor on a new Linux worker stops on the Editor Software Terms dialog (a person accepts it); seed the Library with a batchmode run, which needs no dialog; Linux player builds and RAM numbers from biscuit
---

# A new Linux worker: the terms dialog, the batch seed, the build (w734, biscuit, 2026-10-09)

**Rule.** The first GUI editor on a fresh Linux account opens a "Unity Editor Software Terms"
window and imports nothing until a person accepts it (`xwininfo -root -tree | grep "Software
Terms"` shows it; the editor sits at ~140 MB, no Library, no MCP bridge). It is a legal
acceptance on the person's screen: ask them, never click it. A `-batchmode` run needs no dialog.

**Why.** On biscuit the sandbox editor sat on it for hours while `unity status` said "starting".

**How to apply.**
- Seed the Library meanwhile: `unity-slot run --label X -- ~/Unity/Hub/Editor/<ver>/Editor/Unity
  -batchmode -nographics -quit -projectPath <sandbox> -logFile <tmp>/import.log` (9 min on biscuit,
  0 `error CS`; tests: add `-runTests -testPlatform EditMode -assemblyNames FFEditorTests
  -testFilter <class;class> -testResults <xml>`; the full fast suite took 72 s after that).
- `unity-slot run` refuses while the sandbox's own editor runs (it holds the only slot): stop the
  editor first (`unity stop`, force if it is on the dialog).
- A batch import touches tracked files (`DysonBeam.mat`, the FMOD `libfmodstudio.so.meta`):
  `git checkout --` them, never commit them.
- No Linux build entry exists (`ReleaseBuild.cs` takes Windows and macOS only): a throwaway
  `BuildPipeline.BuildPlayer` method with `-buildTarget Linux64 -executeMethod` built a 2.1 GB dev
  player in ~36 min, almost all shader variants; delete the method after. A player starts through
  `player_slots.py launch <ff.x86_64> -- -batchmode -nographics` (Steam init fails without Steam).
- RAM on a 27 GB laptop (measured): idle 5.9 GB used; batch import peak 20.5; Linux build peak
  22.8 (the editor is 3-5 GB, the shader/Burst helpers the rest). One editor, `max_unity` 1.
- One fast-suite test failed in batch both runs: `AuditWriteCommandTest.ActiveCapturePolicy_TwoWrites…`
  (600-frame wait); unconfirmed whether it is batch-only.

## The editor's bridge, builds from the open editor, and a 1 fps player (w806, 2026-10-09, biscuit/slot1)

- **No bridge on a fresh Linux sandbox** (`[UnityMcpStdioAutoStart] UseHttpTransport pref is unset ... first boot?`, `unity-bridge.py`
  "no MCP for Unity bridge registered"): stop the editor, add `<pref name="MCPForUnity.UseHttpTransport" type="int">0</pref>`
  before `</unity_prefs>` in `~/.local/share/unity3d/prefs` (machine-global; the editor rewrites it on quit, so never with it open),
  start it again: the stdio bridge comes up and `scripts/unity-bridge.py eval_file` works. The MCP tools themselves stay
  disconnected for that session.
- **Never `BuildPipeline.BuildPlayer` from the open editor**: it ran 30 minutes with the bridge answering "Command TCS timed out" and
  no output. A batch build (`unity-slot run -- Unity -batchmode -nographics -quit -buildTarget StandaloneLinux64 -executeMethod
  <your static method>`, editor closed) took 1.5-3.5 minutes. Run named EditMode tests through the open editor with a small
  `ICallbacks` script in `Assets/Editor` (kept out of git) called by `unity-bridge.py eval`; results land in a file you poll.
- **A tour on a PC desktop crawls at 1 fps** (62 frames in 60 s, a 1 fps `record` clip) until `{"fps": 60}` runs: the game turns vsync
  on while it starts, and a window behind others is throttled by the compositor. Set the cap after the first screen is up, not
  at step 1 (`docs/UI-Architecture.md`, "Timing a scroll").
