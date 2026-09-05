---
name: feedback-mcp-bridge-down-recover
description: "If the Unity MCP bridge is unavailable, report it and perform targeted recovery; never silently switch evidence channels or kill broad process groups"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: cd4e6d53-8a75-4415-9d3c-56f75778d16f
---

The first thing to do when a task needs the Unity editor is confirm that the current runtime
exposes the Unity MCP tools and that `mcpforunity://instances` returns an instance whose `path`
is under the current working directory. Claude Code and Codex can both use Unity MCP, although
their tool names and discovery surfaces can differ. Discover the available tools, then pin the
path-matching instance before acting.

If the bridge is unavailable, tell the user what failed and start the targeted autonomous
recovery in the `editor-ops` skill. Resolve the exact checkout from a trusted project path or a
validated Unity process command line. Diagnose with the project-scoped MCP sidecars and the
`unity` CLI, restore stdio or clear stuck MCP state, and restart only the path-verified
project-owned editor if needed. Never kill by a broad Unity process name or touch Unity Hub,
another checkout, or an unresolved process. Return to MCP, re-pin the matching path, and verify
the result there. Escalate only after targeted recovery fails or a real external prerequisite
needs a person.

**Why:** On 2026-07-08 the MCP tools didn't load at session start; I silently used the
file-trigger channel for a whole ForEach→ISystem refactor and only mentioned the gap when
things broke. The user was explicit: "You're supposed to tell me when the MCP isn't
working." The old CLAUDE.md wording actively caused this — it said "run the self-recovery
checklist BEFORE involving the user; only report if that fails," and blessed the file
trigger as a fine fallback, so the gap got absorbed instead of surfaced.

**How to apply:** Announce the degraded bridge promptly, but keep working through the bounded
recovery steps. The `unity` CLI is limited to remote control, recovery, or a runtime where MCP
tools remain unavailable after discovery; state the reason whenever it is used. Do not silently
substitute trigger files, shared `TestResults.xml`, editor-log tailing, or DLL timestamps for an
MCP compile/test result. If MCP cannot be restored in the current session, report exactly which
result was obtained through the CLI and which final MCP verification remains outstanding.
