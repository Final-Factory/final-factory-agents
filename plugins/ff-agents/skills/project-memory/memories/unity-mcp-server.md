---
name: unity-mcp-server
description: How the Coplay MCP-for-Unity server is wired to Claude Code on this Windows machine (stdio transport)
metadata: 
  node_type: memory
  type: project
  originSessionId: 1e630bd9-32e7-437e-8f05-f017495b8dcc
---

The project uses Coplay's **MCP for Unity** plugin (`com.coplaydev.unity-mcp`, pinned in `Packages/manifest.json` — read the tag there rather than quoting a version from here) to let Claude Code drive the Unity editor. Prereqs installed: `uv`/`uvx` and the `claude` CLI in `C:\Users\Lothsahn\.local\bin`.

**Transport = stdio (chosen for multi-instance support).** Claude Code spawns the MCP server as its own child process; the server connects in to the Unity editor's stdio bridge, which listens on a **project-scoped** loopback port (default 6400, file `~/.unity-mcp/unity-mcp-port-<projectHash>.json`). This is the only mode that supports running **two Claude workspaces + two Unity editors at once** without conflict — each project gets its own port + session id (projectHash = SHA1 of `Application.dataPath`; this project's hash is `e5746cd5344953be`). HTTP transport was rejected because its URL lives in GLOBAL per-user EditorPrefs (shared 8080 → cross-talk).

**Why stdio also wins on the other goals:** server is Claude's child → it dies automatically when the session ends (no shutdown hook needed); no shared listening port → the unauthenticated-port security gap doesn't exist (the plugin has no static-key auth anyway — API-key support is remote-hosted-only).

**Claude Code registration (already done, local/project scope in `C:\Users\Lothsahn\.claude.json`):**
`claude mcp add --transport stdio UnityMCP -- "C:\Users\Lothsahn\.local\bin\uvx.exe" --prerelease explicit --from "mcpforunityserver>=0.0.0a0" mcp-for-unity`
- `claude mcp get UnityMCP` "Connected" only means the server binary speaks MCP — it does NOT confirm Unity attachment. Tools work only once the editor is in stdio mode.
- **Tools load only at Claude startup** — restart `claude` in the workspace after registering.

**Editor side (automated):** `Assets/Editor/UnityMcpStdioAutoStart.cs` (`[InitializeOnLoad]`) explicitly calls `StdioBridgeHost.StartAutoConnect()` after the editor goes idle, so the bridge starts on every editor open with no manual step. It only runs when stdio is already selected (`EditorPrefs.GetBool("MCPForUnity.UseHttpTransport", true) == false`) and does NOT change the transport — anyone preferring HTTP is left untouched. The package's own auto-start (`StdioBridgeHost` static ctor → `ShouldAutoStartBridge()`) reads a cached pref whose value depends on undefined `[InitializeOnLoad]` ordering, so it's unreliable on a cold open — this script reads the pref directly instead. First-time/manual path: in `Window > MCP for Unity` set Transport to **Stdio** and start the session; the pref then persists. Script is a no-op if the bridge is already running (checks `StdioBridgeHost.IsRunning`) and skips in batch mode.

**Proving the chain works** means a live read-only tool call round-tripping (e.g. `manage_editor telemetry_status` returning `{"success":true}`) against an instance enumerated by `mcpforunity://instances` with status `running` — not `claude mcp get` saying "Connected". Note the editor status sidecar is `~/.unity-mcp/unity-mcp-status-<shortHash>.json`, not the `unity-mcp-port-*` file named above.

**Multi-instance:** to run a 2nd workspace, register its Claude the same way; if two stdio editors cross-talk, pin each with `--default-instance "<ProjectName>@<projectHash>"`. See [[feedback_test_command]] for the separate test-runner path.
