---
name: judge-a-build-by-marker-and-children-not-editor-cpu
description: "During a player build BOTH editor channels (the unity CLI shim and the MCP bridge) time out and the editor PROCESS can sit near 1% CPU because Bee/IL2CPP/shader compilers run as its children — judge a build by the scheduled-callback marker file's mtime + content, Editor.log growth and `pgrep -P <editor pid>`, never by the editor's own CPU or by a channel timeout; and Editor.log may have ROTATED to Editor-prev.log if another editor started meanwhile."
---

# Judge a build by its marker and child processes, not the editor's CPU (2026-09-12, 069)

- An `eval_file` build (`unity command --project-path <repo> eval_file file=…build_mpdev_all.cs`) writes a
  marker (`mpdev-build-status.txt`: `running <utc>` → `Succeeded errors=0` / failure text). While it runs the
  shim's `editor_status` and the MCP bridge both time out — that is expected, not a wedge.
- The editor's own CPU is NOT a signal: attempt 2 showed 833% only because the 26 Bee/shader children were
  counted; a wedged editor and a building editor can both read ~1%. Distinguish them with `pgrep -P <editor pid>`
  (a build has Bee/`UnityShaderCompiler`/il2cpp children; a modal wedge has none), the marker mtime, and
  `Editor.log` growth.
- `~/Library/Logs/Unity/Editor.log` is per-USER and rotates to `Editor-prev.log` when ANOTHER editor (the clone,
  a relaunch) starts — the build you are watching may now be in `-prev`. Grep both.
- Warm mpdev build ≈ 10-24 min; a platform switch (full shader-graph reimport) ≈ 140 min. Arm a Monitor on the
  marker; never chain sleeps.
- Related: [[build-after-fast-suite-overwrote-main-scene-and-open-scene-checkout-wedge]],
  [[unity-cli-mpdev-build-recipe]], [[unity-editor-log-gotchas]].
