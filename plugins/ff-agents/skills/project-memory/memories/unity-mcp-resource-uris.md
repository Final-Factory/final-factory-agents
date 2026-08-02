---
name: unity-mcp-resource-uris
description: Unity MCP resource URIs use slashes and differ from the resource name field — editor state is mcpforunity://editor/state not editor_state
metadata: 
  node_type: memory
  type: reference
  originSessionId: 5283ba8b-e465-4f26-a90d-3829a4297ca6
---

Unity MCP (`UnityMCP` server) resources: the resource's `name` field is NOT the URI. The
URIs use **slash-separated paths** and often differ from the name. Do not construct a URI by
appending the `name` to `mcpforunity://` — read the `uri` field from ListMcpResourcesTool.

Confirmed URIs (2026-07-05):
- editor readiness snapshot (play mode / isCompiling / activity.phase / advice.ready_for_tools):
  `mcpforunity://editor/state`  (name is `editor_state` — the slash form is correct)
- active Unity sessions: `mcpforunity://instances`
- tests (first page): `mcpforunity://tests`
- project info: `mcpforunity://project/info`
- console errors: use the `read_console` TOOL, not a resource.

See [[unity-mcp-server]].
