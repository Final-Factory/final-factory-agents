---
name: bridge-tcp-fallback
description: How to drive the Unity editor when the session has no MCP tools — raw TCP client to the in-editor bridge on port 6401; execute_code works with Roslyn on this Windows machine
metadata: 
  node_type: memory
  type: project
  originSessionId: 7b78d855-862b-4f39-a416-f34c7531b71a
---

⚠️ **Policy first (CLAUDE.md 🔌/🧯):** a session with no MCP tools must STOP and notify the
user — the sanctioned self-serve diagnostic channel is the `unity` CLI (`com.unity.pipeline`),
not a hand-rolled client. The protocol notes below are for when the user has explicitly asked
to drive the editor this way; the editor-driving facts (Roslyn `execute_code`, reflection UI
clicks, `read_console` buffer order, save loading) hold on every channel.

When a Claude session has no Unity MCP tools (ToolSearch finds nothing), the in-editor
bridge is usually still up: check `~/.unity-mcp/unity-mcp-port-*.json` for the entry whose
`project_path` is `D:/work/FinalFactoryMaster2/Assets` (port 6401) and confirm the port is
listening and owned by the right Unity PID (`Get-NetTCPConnection -LocalPort 6401`).

Protocol (CoplayDev unity-mcp v10, FRAMING=1): TCP connect → server sends
`WELCOME UNITY-MCP 1 FRAMING=1\n` → then frames of 8-byte big-endian length + UTF-8 JSON
`{"type":"<tool>","params":{...}}`. A working Python client lives at (recreate as needed)
a scratchpad `mcp_client.py`; tools used successfully: `manage_editor`
(play/stop), `execute_code` (`{"action":"execute","compiler":"roslyn","code":"..."}`),
`read_console` (`{"action":"get","types":["error"],"count":N,"format":"plain"}`).

Key corrections to the drive-game skill doc (which is macOS-centric):
- `execute_code` WORKS on this Windows machine with `"compiler":"roslyn"` (the old
  "broken on Windows" note applies only to the CodeDom path).
- This copy has NO `DevCommandWatcher`/`DevLoadSave` editor scripts — only
  `TestRunnerTrigger` (run-tests-fast.trigger / test-results.txt) exists as a file channel.
- Dev play mode auto-starts a running game (~60s to IsGameRunning=true).
- `Serialization.SaveGameManager.LoadGame("<name>", true)` loads a save from play mode;
  saves live in `%USERPROFILE%\AppData\LocalLow\Never Games\finalfactory\saves`.
- UI can be driven via reflection from execute_code (internal types: resolve via
  `AppDomain.CurrentDomain.GetAssemblies()` + `asm.GetType("UI.Panels....")`, then
  `FindObjectsByType(type, FindObjectsInactive.Include, ...)`; clicks = `toggle.isOn = true`).
- Roslyn execute_code references ALL loaded game assemblies — direct code like
  `FFCore.Extensions.Ecs.EntityManager.Debug.EntityCount` compiles; reflection only needed
  for internals. "Game is running" check: `FFSystems.Core.ConfigInitializerSystem.GameStarted`
  (static prop; `GameInitializer` has NO IsGameRunning member).
- `read_console` `{"action":"get","count":N}` returns from the START of the buffer, not the
  tail — to find recent lines use `"filterText":"..."` (supports spaces; pass params from a
  Python script, PowerShell quoting mangles embedded spaces).
- Load-complete markers in console: "Loading <N> entities time:", "Loaded game with seed".
- This copy runs with 5 workshop mods loaded (AutoLoot, Collector, ItemCannon,
  MobileStationTweaks, RandomMovementExample) — vanilla saves with unmodded item ids can fail
  InstantiateEntity with "Item prefab ... does not have AsteroItem component"; use "bug 3"
  (or another save made on this copy) for load tests, NOT the _autosave_* slots.
