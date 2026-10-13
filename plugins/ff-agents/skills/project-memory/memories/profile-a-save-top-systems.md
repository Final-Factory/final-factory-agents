---
name: profile-a-save-top-systems
description: "\"Profile this save, give me the top N systems\": the bench player (Editor.ShaderBenchBuild, FF_SHADER_BENCH) with -ffBench save:<name> -ffBenchSystems 1, analysed with scripts/bench/analyze_systems.py; rank fixed-tick and per-frame systems together by main-thread ms per second, because a per-frame system's p95 exists only over heartbeat frames; the worker-job markers came back empty on a Windows player; no wmic on beast."
---

# Profiling a player's save for its top systems (2026-10-13, w1199 LifeSave)

lothsahn: "Please profile this save to see which systems are taking the most time. Give me the top 20 systems". The
repo already has the tool. Nothing new was needed, and the whole run took about 25 minutes on beast:

1. **Build** the bench development player in batchmode into `$TMPDIR`. With the sandbox editor stopped, run
   `unity-slot run --label "<what>" -- "<Unity.exe>" -batchmode -quit -projectPath <worktree> -buildTarget Win64
   -executeMethod Editor.ShaderBenchBuild.BuildWindows -ffBenchBuildOutput "$TMPDIR/benchbuild/player/finalfactory.exe"
   -logFile …`. It took about 15 minutes. Burst is AOT: `lib_burst_generated.dll`, with
   `BurstAotSettings_StandaloneWindows.json` (optimisations on, safety checks off). "Synchronous" is an editor-only
   setting: a player has nothing compiling at runtime.
2. **Copy the save** into the saves folder as `ffa-<session>-<name>.zip`. Then **launch through the slot pool**
   (`source scripts/nightly/player_launch.sh`; `"${FF_LAUNCH[@]}" <exe> -- -screen-fullscreen 0 -screen-width 1280
   -screen-height 720 -ffBench save:ffa-<session>-<name> -ffBenchSystems 1 -ffBenchFly 0 -ffBenchSeconds 180
   -ffBenchOut <dir> -logFile <dir>/player.log`). The bench loads the save solo, waits 10 s and records the window. It
   also switches vsync off and lifts the frame cap, saves nothing, and quits by itself.
3. **Analyse** with `python scripts/bench/analyze_systems.py <dir>/save-idle`, which ranks per heartbeat frame.
   `save-idle-systems.csv` has, per marker, `hb_mean/p50/p95/p99/max` over heartbeat frames, plus only a mean for the
   other frames. To rank fixed-tick and per-frame systems together, use main-thread ms per second:
   `hb_mean*hb_frames + other_mean*other_frames`, over the window. Walk `parent` up to an `FFFixed*` group to tell
   the fixed tick from per-frame work. A per-frame system's p95 is only over the heartbeat frames: say so.

Traps seen in w1199:

- **Per-frame systems scale with frame rate.** The bench runs uncapped (87 fps on LifeSave), so per-frame systems
  outrank fixed-tick ones by ms/s. A player with vsync on runs fewer frames. Give the fixed-tick top list
  (per heartbeat) beside the combined one.
- **Some per-frame systems show the job wait, not their own work.** On non-heartbeat frames,
  `ProjectileParticlePresentationSystem` (`CompleteDependencyBeforeRW<LocalToWorld>`) and `MouseRaycastSystem`
  (the CollisionWorld) cost 0.6 ms against 0.07-0.09 ms on heartbeat frames. Times are inclusive of `JobHandle`
  waits.
- **The `jobs ` worker markers were empty.** `SystemFrameRecorder` registered 1,537 job markers on the Windows
  player, and none recorded a sample: the CSV has no `jobs ` rows. For worker-thread time, use `-ffBenchProfile 1`
  and `scripts/bench/rawreader`. Not investigated further.
- **No `wmic` on beast** (Windows 11 26200), so a contention log built on it prints nothing. List other
  `finalfactory.exe` with `tasklist`, and batch editors with `unity-slot status`.

Related: [[measure-a-systems-cost-in-a-built-player]], [[heartbeat-perf-a-removed-wait-moves-to-the-next-system]],
[[beast-shared-machine-perf-ab-side-by-side]].
