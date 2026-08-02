---
name: feedback-mcp-bridge-down-stop
description: "If the Unity MCP bridge isn't up, STOP and tell the user first — never silently use the file-watch fallback"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: cd4e6d53-8a75-4415-9d3c-56f75778d16f
---

The FIRST thing to do when a task needs the Unity editor: confirm the MCP bridge is up
(the `mcp__UnityMCP__*` tools are loaded AND `mcpforunity://instances` returns an instance
whose `path` is under the current working directory). **If it is not up, STOP and tell the
user immediately as an explicit blocker — do NOT quietly fall back to the file-watch
triggers (`run-tests*.trigger` / `test-results.txt`).**

**Why:** On 2026-07-08 the MCP tools didn't load at session start; I silently used the
file-trigger channel for a whole ForEach→ISystem refactor and only mentioned the gap when
things broke. The user was explicit: "You're supposed to tell me when the MCP isn't
working." The old CLAUDE.md wording actively caused this — it said "run the self-recovery
checklist BEFORE involving the user; only report if that fails," and blessed the file
trigger as a fine fallback, so the gap got absorbed instead of surfaced.

**How to apply:** Check the bridge up front and announce a down bridge right away. The
`mcp__UnityMCP__*` tools load only at Claude startup (see [[unity-mcp-server]]), so a bridge
down at session start cannot be self-recovered mid-session — ask the user to run `/mcp`
(reconnect) and confirm the editor transport is Stdio (`Window > MCP for Unity`), then
re-read `mcpforunity://instances`. Use the file-watch fallback ONLY after telling the user
and getting their explicit OK. (CLAUDE.md's "🔌 Build & Test" block was rewritten to match
this on 2026-07-08.)
