---
name: profile-a-whole-frame-with-the-in-player-log
description: "Profiling a save's whole frame (main, render thread, job workers, GPU, draw calls): use the bench's in-player profiler log (-ffBenchProfile 1), not an editor-connected capture, which distorted LifeSave's frame (15 ms against 10.2, waits moved, two UI LateUpdates read 4.6 ms against 0.34) and recorded no rendering counters; count job waits by the inclusive time of the outermost wait; the bench CSV's heartbeats column marks the frame after the heartbeat."
---

# Profiling a whole frame: the in-player log, not the editor connection (2026-10-13, w1204 LifeSave on beast)

lothsahn: "You mentioned that simulation is 6.5ms per tick and most of the time goes to per-frame rendering and visual
effects. Can you get me a profile of that section of the game?" The recipe that worked on beast (i9-14900KF, RTX 4080
SUPER, D3D11, 3840x2160 High):

1. The bench player and save as in [[profile-a-save-top-systems]].
2. **The comparable run:** `-ffBench save:<name> -ffBenchSystems 1 -ffBenchSeconds 180 -ffBenchFly 0`, no profiler.
   Its `save-idle-systems.csv` (ProfilerRecorder per marker) is the number to quote.
3. **The breakdown run:** the same with `-ffBenchProfile 1 -ffBenchSeconds 30`. It writes `save-idle.raw` in the
   player itself (`Profiler.logFile`): 1.5 GB for 30 s, about 2,000 frames. On LifeSave it cost 0.15 ms on the frame
   median (10.37 against 10.22 ms, measured). It agreed with the recorder system by system (MouseRaycast 44.9 against
   46.0 ms/s), and it carried what the editor capture lacked: `Draw Calls Count`, `Batches Count`, `SetPass Calls
   Count`, `Triangles Count`, `GPU Frame Time` and `CPU Render Thread Frame Time`. Read them with
   `ProfilerDriver.GetCounterValuesBatch(ProfilerArea.CPU, "<name>", firstFrame, 1, buffer, out max)` after
   `LoadProfile`; `RawFrameDataView.HasCounterValue` said no for them.
4. **Digest** in an empty project under `$TMPDIR` (scripts/bench/rawreader's one-time setup, `unity-slot run`,
   batchmode): walk every thread of every frame with `GetRawFrameDataView(frame, t)`. The render thread is
   `threadName == "Render Thread"`; job workers are `threadGroupName == "Job"`. Leave out their `Idle` samples and
   the unnamed root sample (about 14 ms a frame across 31 workers) from job time.

Traps:

- **An editor-connected capture distorts the frame.** This is `capture_raw.sh` / `ProfilerCapture`, or any
  `DirectIPConnect`. On LifeSave the captured frame was 15 ms against 10.2 unprofiled. The job waits moved out of the
  ECS systems: MouseRaycast read 0.11 ms against 0.66. `BottomHudFlow.LateUpdate` plus
  `StationHoverInfoPanel.LateUpdate` read 4.6 ms a frame, while the bench's own recorder in the same player and the
  same seconds read the whole `PreLateUpdate.ScriptRunBehaviourLateUpdate` stage at 0.34 ms. The in-player log showed
  0.34 too. So do not rank items from an editor capture; use it at most for shares.
- **The editor capture recorded no rendering counters and no GPU samples.** This held even with
  `ProfilerDriver.SetAreaEnabled(Rendering/GPU, true)` and `profileGPU = true` set before the connection.
  Per-marker GPU time (`HierarchyFrameDataView` columns 8 and 9, `columnTotalGpuTime` and `columnSelfGpuTime`, which
  are internal) was 0 in the in-player log too, on D3D11. The GPU total comes from `GPU Frame Time` or from the
  bench's `gpu_ms` (FrameTimingManager).
- **Count job waits by INCLUSIVE time.** The main thread runs jobs inside `WaitForJobGroupID`, so the wait marker's
  self time understated the waiting about 3x (0.67 against 2.2 ms a frame). Take the outermost `JobHandle.Complete` /
  `WaitForJobGroupID` and charge its inclusive time to the innermost ECS system above it.
- **The bench's `<window>.csv` `heartbeats` column is one frame late.** MonoBehaviour Update runs before the ECS
  simulation, so the column marks the frame after the one that ran the heartbeat. Splitting wall time by it showed
  heartbeat frames cheaper (9.6 against 10.5 ms). The real pattern is four frames of about 10 ms, then one of about
  21 ms. `SystemFrameRecorder`'s `-hb.csv` rows are aligned correctly (wall about 21 ms).
- **`PostLateUpdate.ProfilerEndFrame` (0.3 ms a frame) exists only while profiling.** Leave it out of the breakdown.
- **beast never went quiet** during w1204: there was always a Deck-tour player (w1155) or an agent-control player.
  Record contention every 30 s (`Get-CimInstance Win32_Process` for finalfactory.exe and Unity.exe, plus a CPU delta
  per process). Repeat the comparable run and check that it matches the earlier one, rather than wait hours. w1204's
  run matched w1199 within 5% per system.
- **A development player without the bench refuses `-ffBench`, and `capture_raw.sh` does not run on Windows** (w2163,
  beast, 2026-10-25). `scripts/nightly/build_player.sh` builds no `FF_SHADER_BENCH`, so `-ffBenchProfile` is not
  there. `capture_raw.sh`'s self-relaunch `bash` resolved to WSL's `System32\bash.exe`, and it hands POSIX paths to the
  player. What worked: a solo run through `player_slots.py launch` inside `bench_lock --timing`, with
  `-profiler-enable -profiler-log-file "$(cygpath -w $OUT/cap.raw)" -ffAutomationRole solo -ffAutomationSave <save>
  -ffAutomationPostReadyCommand "ffauto:wait|2;ffauto:perf.sample|15|20;ffauto:wait|20" -ffAutomationAutoQuit true`.
  Then digest it under `unity-slot run` in the rawreader project with `-batchmode -nographics -quit -executeMethod
  HeartbeatTimeline.Batch -htLog <raw> -htOut <txt>`. Its per-heartbeat job table and whole-frame critical chain
  named a serial worker job the frame waited for: `ExecuteShipSpawnCommandJob`, 28.9 ms mean and 113.7 ms p95 a
  heartbeat on The Meanie's save. For the before/after, use `scripts/bench/probe_ab_win.sh` with `CHAIN=` set to the
  same perf.sample.

Related: [[profile-a-save-top-systems]], [[heartbeat-perf-a-removed-wait-moves-to-the-next-system]],
[[beast-shared-machine-perf-ab-side-by-side]].
