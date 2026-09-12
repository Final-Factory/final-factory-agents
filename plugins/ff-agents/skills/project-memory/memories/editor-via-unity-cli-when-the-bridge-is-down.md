---
name: editor-via-unity-cli-when-the-bridge-is-down
description: "The `unity` CLI shim (~/.local/bin/unity) is a full substitute for the UnityMCP bridge when it fails to connect (CONNECT_TIMEOUT while the editor is mid-build): recompile/recompile_status, eval/eval_file (Roslyn statements, no using directives), editor_play/editor_stop, get_console_logs, run_tests/test_status, and a guarded EditorApplication.update callback for MP-dev builds; plus the ItemConfig-before-LoadGame gate and the stale bundled status file."
---

# Driving the editor through the `unity` CLI when the MCP bridge is down (2026-09-12, 069)

**When.** The UnityMCP bridge reported `CONNECT_TIMEOUT` at session start for a whole session
(the editor was mid-IL2CPP build). Nothing was lost: every editor operation ran through
`~/.local/bin/unity` against this repo's editor (`unity status --project-path <repo>`; port 7800 =
the main checkout, 7801 = `_clone_0`). Form: `unity command --project-path <repo> [--timeout s]
[--json] <cmd> [args]`.

**Commands that carried a full session.**
- `recompile`, then poll `recompile_status` until `"status":"completed"` and `"failed":false`.
- `eval --code '<statements>'` / `eval_file --file <abs .cs>` (the flag is `--file`, not `file=`):
  Roslyn STATEMENTS only — no `using` directives, fully-qualify every type, `return` a string.
  Wrap with a helper that parses the `--json` envelope (`data.result` is itself a JSON string with
  `success`/`result`/`error`/`errorDetails`).
- `editor_play` / `editor_stop`; `get_console_logs --severity error|warning --limit N`.
- `run_tests --mode EditMode --filter FFEditorTests --filter_type assembly --async_tests` then
  `test_status` (fast suite ≈ 10 min; its JSON is malformed for one test name — parse loosely).
- MP-dev build without the bridge: `eval_file` a script that (a) refuses if playing/compiling,
  (b) writes a once-guard file, (c) registers an `EditorApplication.update` callback that
  unregisters itself, sets `PlayerSettings.bundleVersion = FFVersion.FinalFactoryVersion`, runs
  `Editor.BuildCommand2.BuildWindowsMultiplayerDev()` then `BuildOsxMultiplayerDev()`, checks
  `BuildReport.GetLatestReport().summary` (`Succeeded` AND `totalErrors == 0`), and writes a marker
  file `running-windows … → running-osx … → returned …` / `failed: …`. Poll the marker; verify the
  output `FFSystems.dll` mtimes are post-start. Never via `execute_menu_item`.

**Single-player repro recipe through it.** `editor_play` → wait until an `FFCore.Config.ItemConfig`
singleton exists (calling `LoadGame` earlier throws and nothing loads) →
`Serialization.SaveGameManager.LoadGame(FFNetcode.Lobby.LobbyCreationParameters.SinglePlayerGame, "<save>", true)`
→ wait `PlayerController.PlayersManager.LocalPlayerReady` → drive with
`Behaviours.Multiplayer.LocalMultiplayerAutomationCommandRunner.TryExecute("ffauto:…", out r)`.
A save taken by the host loads with the local player = the CLIENT's player in single-player
(inventories differ — `inventory.add|…` what the repro needs). `player.setposition` takes TILES.

**Trap.** A staged built-player bundle ships a STALE `.ff-local-automation-status.json`; ignore
status entries whose `UpdatedAtUtc` predates the launch. Related: [[feedback_mcp_bridge_down_stop]]
(report the gap, recover the exact editor) — the CLI is the sanctioned substitute, not file evidence.
