---
name: unitymcp-per-project-config
description: "The Unity MCP bridge (server \"UnityMCP\") is configured per-project in ~/.claude.json; FinalFactoryMaster was missing it"
metadata: 
  node_type: memory
  type: reference
  originSessionId: a4d875de-4479-40ba-86a3-b60d104644e3
  modified: 2026-07-18T23:05:49.923Z
---

The Unity editor bridge tools (`mcp__UnityMCP__*`, aka mcp-for-unity) surface in a Claude Code
session only if the **`UnityMCP`** server is configured for that project in
`~/.claude.json` under `projects.<path>.mcpServers`. It is set **per-project**, not globally.

FinalFactoryMaster had an **empty `mcpServers`** (both the `D:\work\FinalFactoryMaster` and
duplicate `D:/work/FinalFactoryMaster` keys), unlike FinalFactory / FinalFactory2/3/4 /
FinalFactoryMaster2 which all had it — so the bridge never launched here and no tools appeared
no matter how many restarts. Fix (run from the project dir, then restart Claude Code):

```
claude mcp add UnityMCP -- "C:/Users/Lothsahn/.local/bin/uvx.exe" --from mcpforunityserver==10.0.0 mcp-for-unity
```

Notes: MCP servers attach only at session **startup** (no hot-attach mid-session — restart).
The Unity-side bridge being "running" in the editor is separate from the Claude-client config.
Diagnose absence via: `mcp-logs-UnityMCP` folder under
`AppData/Local/claude-cli-nodejs/Cache/<project>/` (missing = never launched), and the fresh
`~/.unity-mcp/unity-mcp-port-*.json` (editor bridge is up). Related editor-readiness rule lives
in CLAUDE.md's "Step 0 — FAIL FAST". See also [[playmode-needs-main-scene]].
