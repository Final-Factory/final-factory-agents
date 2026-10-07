---
name: pipeline-warmup-trace-in-a-development-player
description: "w604 (2026-10-07): the boot shader/pipeline warm-up lists (StreamingAssets/PipelineWarmup, -ffBenchTracePso) must be traced in a DEVELOPMENT bench player: a Release player's GraphicsStateCollection trace starts (BeginTrace true) but saves 0 variants and 0 states, on Direct3D 11 and 12. Direct3D 11 traces variants only and its warm-up runs on the main thread, so PipelineWarmup spreads it over frames."
metadata:
  type: project
---

Source: w604 / w556 (Windows lists), PR #1196, on lothdesktop (Intel Arc B580); w530 (#1141) and w557 made the Mac
lists. Code: `Assets/Scripts/Behaviours/PipelineWarmup.cs`, the trace in
`Assets/Scripts/Behaviours/Bench/ContentShaderBench.Roam.cs` (`-ffBenchTracePso <file> -ffNoPipelineWarmup`),
builds in `Assets/Editor/ShaderBenchBuild.cs`.

**Trace in a Development player.** `ShaderBenchBuild.BuildWindowsRelease` / `BuildMacRelease` players trace nothing:
`BeginTrace()` returns true, `SaveToFile` succeeds, and the file holds 0 variants and 0 states (measured on
Direct3D 11 and Direct3D 12). The Development player of the same commit (`BuildWindows` / `BuildMac`) records them
(Medium content bench: 152 variants on D3D11; 73 variants and 90 states on D3D12). Measure the before/after in the
Release player, with the Development player's lists copied into its `finalfactory_Data/StreamingAssets/PipelineWarmup`.
The trace logs `pipeline trace started <bool> on <API> (parallel PSO creation …, development …)`: check it first.

**Direct3D 11 (what Windows ships).** No parallel PSO creation, so a trace holds variants only (0 states), and
`GraphicsStateCollection.WarmUp` falls back to the legacy shader-variant warm-up on the main thread (Unity docs).
`PipelineWarmup` therefore calls `WarmUpProgressively(2)` once per frame for `ceil(variants / 2)` frames there;
`isWarmedUp` cannot end the loop on a collection with no states. Cold driver cache: 3.0 s for a 187-variant list,
longest frame step 8 ms. `completedWarmupCount` reports only ~80 of ~190 variants, run after run, and why is not
settled. Judge the warm-up by the roam hitches, not by that count. `-force-d3d12` works in a D3D11-only player if a
state trace is ever wanted.

**Cold cache on Windows/Intel.** The driver keeps one shader cache file per app, not per build:
`%USERPROFILE%/AppData/LocalLow/Intel/ShaderCache/e3486dfa…b183` for finalfactory on lothdesktop.
`scripts/bench/roam_hitches.sh` deletes it under `COLD=1` (`WIN_SHADER_CACHE`). Every finalfactory player on the PC
shares it: set the original aside first and put it back when done.
