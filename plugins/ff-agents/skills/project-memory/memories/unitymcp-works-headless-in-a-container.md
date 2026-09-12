# UnityMCP DOES work headless in an ffbox container — proven 2026-09-11, with the two gotchas

Measured on the build server, not reasoned about: a batchmode editor in an ffbox container served
46 MCP tools to the packaged Python server, and a real `read_console` call came back with live
editor state. The editor stayed alive through the calls. So "the container cannot use the MCP
bridge" is false, and the blockers are all on our side of the line.

**The proven recipe.** Four pieces, and every one of them is required:

1. **The server, baked into the image.** It is the PyPI package `mcpforunityserver` (console
   scripts `mcp-for-unity` and `unity-mcp`), driven by `uv`/`uvx`. Install it at image BUILD time
   with shared paths so the run user can reach it — `UV_INSTALL_DIR=/usr/local/bin`,
   `UV_TOOL_BIN_DIR=/usr/local/bin`, `UV_TOOL_DIR=/opt/uv/tools`,
   `UV_PYTHON_INSTALL_DIR=/opt/uv/python`. Verified to run under `--network none` afterwards, which
   is the point: nothing resolves from PyPI at run time, so the egress fence needs no new hosts.
2. **`UNITY_MCP_ALLOW_BATCH=1`.** `StdioBridgeHost`'s static constructor RETURNS EARLY in batchmode
   without it (`Editor/Services/Transport/Transports/StdioBridgeHost.cs`), so the keep-alive hooks
   never get installed. This is the switch that makes a headless editor serve.
3. **`-executeMethod MCPForUnity.Editor.McpCiBoot.StartStdioForCi`, and no `-quit`.** `McpCiBoot` is
   a public CI entry point in the package: it forces HTTP transport off and calls
   `StdioBridgeHost.StartAutoConnect()`. Without `-quit` the editor stays up and keeps serving.
4. **Kill the editor as a PROCESS GROUP.** `unity-editor` in the image is an `xvfb-run` wrapper;
   SIGTERM to the wrapper pid reparents the real editor to init, where it holds the Unity licence
   seat. Launch under `setsid`, kill `-- -PGID`. Same lesson as
   [ffplaytest](ffbox-containers-can-run-unity.md).

**GOTCHA 1 — the port registry file is not the readiness signal.** `PortManager` writes
`~/.unity-mcp/unity-mcp-port-<hash>.json` only when it has to move OFF the default port, so a
bridge that gets 6400 publishes nothing. A probe that waited for that file called a working bridge
a failure. **Wait for the editor log line** `StdioBridgeHost started on port <N>` instead — that is
the supported signal, and it also tells you the port.

**GOTCHA 2 — telemetry.** The package posts telemetry unless `DISABLE_TELEMETRY`,
`UNITY_MCP_DISABLE_TELEMETRY` or `MCP_DISABLE_TELEMETRY` is set. Behind the egress fence the call
cannot succeed anyway, and a blocked outbound call is a stall waiting to happen. Set it.

**Numbers from the run.** A blank project with the package embedded: 78s to load (70s of it asset
database refresh), bridge up ~10s after that on a warm second boot, 46 tools including
`execute_code`, `read_console`, `batch_execute`, `manage_asset`. FinalFactory will be
substantially slower — 2401 scripts, Burst, a real domain reload — and that cost, not
feasibility, is what a design has to answer for: whose clock pays for the boot, and whether the
bridge survives a domain reload in batchmode.

**Still unproven, and worth knowing before relying on it:** the same recipe against the real
FinalFactory workspace (only a blank project was used), bridge survival across a domain reload
(recompile mid-turn), and two editors in one container.

Related: [an ffbox container can run Unity](ffbox-containers-can-run-unity.md) for why the prompts
used to deny this, and [two docker daemons](ffbox-two-docker-daemons.md) — the probe only works
with `DOCKER_HOST=unix:///run/ffbox-container/docker.sock`.
