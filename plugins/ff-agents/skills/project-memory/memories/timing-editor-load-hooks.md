# Timing each [InitializeOnLoad] hook, locally and on CI

**What.** `Editor.log`'s `Domain Reload Profiling` block shows only totals
(`ProcessInitializeOnLoadAttributes`, `ProcessInitializeOnLoadMethodAttributes`). To get one line
per hook, profile the editor's own startup. Each `[InitializeOnLoad]` static constructor and
`[InitializeOnLoadMethod]` is already a profiler sample (`<Assembly>.dll!<Type>..cctor()`), so you
don't need deep profiling to rank them. Deep profiling is only for looking inside one slow hook.

**Recipe** (w533, 2026-10-06; Unity 6000.3.19f1):

1. Launch the project with
   `-batchmode -profiler-enable -profiler-log-file <x>.raw -profiler-maxusedmemory 1073741824 -quit`,
   adding `-deepprofiling` for internals. A raw file is about 0.3–1.4 GB plain and up to 20 GB deep.
2. Load the raw file in any other project (a fresh `-createProject` scratch project is fine) with
   `-executeMethod`:
   `ProfilerDriver.LoadProfile(raw, false)`, then `ProfilerDriver.GetRawFrameDataView(f, 0)` for
   each frame. Walk the samples using `GetSampleChildrenCount` to track depth. Print every sample
   under `SetupLoadedEditorAssemblies` with `GetSampleTimeMs`. Samples come out in call order, so
   you can line them up with the timestamps of log lines (`HierarchyFrameDataView` sorts by time
   instead).
3. To run it on CI, use `workflow_dispatch` of `main.yml` on a throwaway branch that replaces the
   test command. That needs no PR and doesn't write the cache, because only the nightly
   `rebuild-caches.yml` writes it. Print the dump into the job log. The dumper used for w533 is
   `timing-editor-load-hooks-dump.cs.txt` beside this note: drop it into `Assets/Editor/` as `.cs` and pass
   `-w533Spec "<raw>|<minMs>|<maxDepth>[|<ancestor filter>];..." -dumpOut <file>`.

**What it found on the ffgithubrunners editmode job** (measured per launch, two runs each):

- `Unity.Burst.Editor.BurstLoader..cctor`: 10.3–13.6 s on CI, 0.4 s on an M3 Mac. Almost all of
  it is `CacheManager.LoadCache`, which parses the manifest of the 1.4 GB, 3,778-file
  `Library/BurstCache` and reads assemblies with Cecil. A second launch in the same job is no
  faster.
- `--burst-disable-compilation` removes that cost: the launch drops from 50 s to 33 s. But the
  full EditMode suite then took 723 s instead of 454–547 s, because jobs run in Mono, and it was
  still green. So disabling Burst is a net loss for CI.
- MCP for Unity v10.0.0 `TransportCommandDispatcher..cctor` (`CommandRegistry.AutoDiscoverCommands`,
  a reflection scan over every type): 4.9–6.1 s on CI, 0.7 s on a Mac. v10.2.0+ uses `TypeCache`
  (PR #1136).
- `Unity.Pipeline.Editor.PipelineServerStartup..cctor` (package removed 2026-10-06, w533 / PR #1154; com.unity.pipeline started an HTTP server
  on :7800): 1.0–1.7 s on CI, 0.35 s on a Mac.
- `Unity.Entities.BindingRegistry..cctor` (TypeManager init): 1.1–2.1 s on CI. It's needed anyway.
- `RiderScriptEditor..cctor`: 0.88 s per reload on a Mac (install discovery), 0.01 s on CI.
- The first domain reload of a cold CI launch loads only Unity's own assemblies. 11 s of it is in
  Unity's `DesktopLinuxToolchainMigrator.RemoveLegacyPackages` → `WaitRequestsToComplete`, which
  waits on Package Manager requests. It's 2.4 s on a warm launch. That's package resolution, not
  project code.
- The project's own hooks (`Assets/Editor/*`, `TraceState`, `DeterminismJobOrderProbe`) each take
  under 30 ms on CI. Look in packages first.

**Traps.**

- Step durations of CI runs that share the host with other runs are not comparable: the same
  suite took 454 s alone and 537–547 s next to profiling probes. Compare per-hook samples instead.
- A batchmode launch from a worktree whose `Library` was copied from another branch recompiles
  once. Throw that launch away before timing warm launches.
