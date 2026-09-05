# Profiling ECS systems + package-fork pin bumps (030 lessons, 2026-07-21)

Two durable operational recipes from the 030 KNN performance lane.

**Fork/package pin bumps with a ParrelSync clone** (Windows box, where the clone's
`Packages/` is a REAL directory, NOT a symlink):

- Copy `manifest.json` + `packages-lock.json` into `<project>_clone_0/Packages/`.
- Run `UnityEditor.PackageManager.Client.Resolve()` via `execute_code` on the CLONE instance —
  `refresh_unity` does NOT trigger UPM resolution.
- Then verify BOTH editors picked it up: `Library/PackageCache/<package>@<sha>` exists AND
  `ScriptAssemblies/<assembly>.dll` has a fresh mtime. The first reload after a pin bump can
  compile BEFORE the package content lands — tests then run stale with varying-garbage
  failures.

**Profiling ECS system cost in-editor:**

- On Unity 6000.3.19f1 at game revision `7d696256c`, `ProfilerRecorder` CAN sample the system
  markers. Resolve a `ProfilerRecorderHandle` for `Scripts/TimeNanoseconds`, named `Default World
  <FullTypeName>`, then create a capacity-one `ProfilerRecorder` from that handle with
  `StartImmediately | SumAllSamplesInFrame | WrapAroundWhenCapacityReached |
  CollectOnlyOnCurrentThread`; capture the completed-frame sample. Source:
  `Assets/Scripts/Behaviours/Multiplayer/PerfProbe.cs` — `CreateSystemRecorders` and
  `CaptureSystemFrame`; `Assets/Scripts/Behaviours/Multiplayer/PerfProbeAggregator.cs` —
  `PerfSystemAggregator.BuildSummary`. Do not generalize this result to other Unity versions,
  revisions, recorder options, marker names, or threads.
- It produced nonzero samples in M5 EditMode (5 frames), BEAST 60-second flat (10,170 frames,
  240 systems), and camps (3,827 frames, 245 systems): 416 handles and zero invalid handles in
  both BEAST runs. Evidence: `/private/tmp/ff-perf-recorder-spike-20260905.md` and BEAST
  `C:/Users/rydin/ff-worker/profile-sweep14-7d696256c/perf-{flat,camps}`.
- The samples are main-thread inclusive and nested, so they are not additive. They do not assign
  GC or job-worker time. Instrumented audit runs are diagnostic measurements, not production
  performance budgets. Keep the `ProfilerDriver.enabled` + `GetRawFrameDataView` route as the
  fallback when this exact recipe does not apply (and set `ProfilerDriver.enabled` directly;
  `manage_profiler` start once reported success without enabling it).
- The occluded-editor player-loop freeze applies on Windows too: pump with
  `EditorApplication.Step()` while paused. Never unpause a monster save with
  `runInBackground=true` — multi-second frames starve the MCP bridge into timeouts.
