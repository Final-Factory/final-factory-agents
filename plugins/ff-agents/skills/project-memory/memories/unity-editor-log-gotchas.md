---
name: unity-editor-log-gotchas
description: "Reading Unity Editor.log on this machine — line numbers are unreliable, slice with awk after a marker, and map bridge port to PID to find the right editor"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 822bc922-d77f-4c91-8be4-7e361f39d590
  modified: 2026-07-25T23:08:36.344Z
---

`C:/Users/Lothsahn/AppData/Local/Unity/Editor/Editor.log` on this machine (verified 2026-07-25
while checking connector changes against the Wittlebase / MeltCPU saves):

- **Line numbers are NOT trustworthy.** The file contains binary/NUL stretches, so `grep -a -n`
  and `wc -l` disagree badly — `grep` reported a marker at line 36044 in a file `wc -l` called
  207,455 lines. Slicing with `sed -n 'N,$p'` off a `grep -n` number silently reads the wrong
  region; I "found" a NullReferenceException that was really from an earlier test run.
  **Slice after a marker with `awk '/MARKER/{f=1} f' Editor.log`**, never by line number.
- **Grep with `-a`** or it reports "Binary file matches" and prints nothing.
- **Drop a marker before an action** you'll want to isolate later:
  `UnityEngine.Debug.Log("CLAUDE_<thing>_START ...")` via `execute_code`, then `awk` from it.
- **Several Unity processes write here.** A tail can show a *player build* from a different
  process (its `##utp:{"type":"PlayerBuildInfo","processId":N}` names the builder), which reads
  like the editor is idle/stale when it isn't. Don't infer the editor's state from a tail alone.
- **Identify THIS project's editor by port, not by CPU or guesswork:**
  `Get-NetTCPConnection -LocalPort 6401 -State Listen` → OwningProcess, cross-checked against
  `~/.unity-mcp/unity-mcp-port-<hash>.json` (`project_path`, `unity_port`) for the hash of the
  pinned MCP instance. Port files can collide across copies, so trust the live listener + the
  MCP instance list. I picked a PID by "highest CPU" once and was profiling the wrong process.
- **A saturated main thread freezes the bridge without hanging the editor.** `editor/state` keeps
  answering but `sequence` stops advancing and `execute_code` times out. Flat memory + steady CPU
  = working hard, not deadlocked. MeltCPU (129k entities) does this for the whole load.
- **The game logs its own load timings**: `===== LOAD PROFILE: <save> =====` with a phase table —
  the authoritative source for load timing, better than wall-clock guessing.

Related: [[watch-logs-without-full-scans]], [[bridge-tcp-fallback]].
