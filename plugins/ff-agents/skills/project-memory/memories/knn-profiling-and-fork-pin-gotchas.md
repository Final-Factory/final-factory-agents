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

- `ProfilerRecorder` never samples system markers — use `ProfilerDriver.enabled = true` (set
  the property directly; `manage_profiler` start reported success without actually enabling
  it) + `GetRawFrameDataView` per-invocation extraction.
- The occluded-editor player-loop freeze applies on Windows too: pump with
  `EditorApplication.Step()` while paused. Never unpause a monster save with
  `runInBackground=true` — multi-second frames starve the MCP bridge into timeouts.
