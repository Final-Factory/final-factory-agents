---
name: project-memory
description: Accumulated Final Factory project memory — hard-won lessons about the Unity MCP bridge, Burst/ECS gotchas, baking, modding ABI, screenshot/play-mode traps, and standing user feedback (test commands, no-cd rule, bridge-down = stop). Consult BEFORE debugging the MCP bridge, running tests, entering play mode, editing open scenes, diagnosing Burst NREs after a merge, or working on mod loading. Also the place to CHECK FIRST when something in the editor behaves inexplicably.
---

# Final Factory project memory

One file per lesson under `memories/`. Read the entry for the area you are touching before
re-deriving anything the hard way. These were accumulated across the develop and master
worktrees and apply to ALL branches.

## Standing user feedback (always applies)

- [Use standard test commands](memories/feedback_test_command.md) — run tests via MCP `run_tests`/`get_test_job` (pinned instance); the file-trigger channel is retired for routine runs
- [MCP bridge down = stop](memories/feedback_mcp_bridge_down_stop.md) — if the Unity MCP bridge isn't up, STOP and tell the user first; never silently use the file-watch fallback
- [No cd prefix in Bash](memories/feedback_no_cd_prefix.md) — never prefix commands with `cd` into the working dir; it triggers approval prompts, use paths directly
- [Drive interactive verification myself](memories/drive-interactive-verification.md) — I CAN run/screenshot the app and drive paired multiplayer/determinism audits; don't punt visual/interactive checks to the user

## Unity MCP bridge

- [Unity MCP server](memories/unity-mcp-server.md) — Coplay MCP-for-Unity via stdio (multi-instance safe); Claude spawns server, editor must be set to Stdio transport in Window>MCP for Unity; tools load only at Claude restart
- [Unity MCP resource URIs](memories/unity-mcp-resource-uris.md) — resource URIs use slashes and differ from the `name` field; editor readiness is `mcpforunity://editor/state` NOT `editor_state`; read the `uri` field, don't build from name
- [UnityMCP per-project config](memories/unitymcp-per-project-config.md) — the Unity bridge tools require a per-project UnityMCP server in ~/.claude.json (claude mcp add + restart)
- [Verify compile via DLL string check](memories/verify-compile-dll-string-check.md) — refresh_unity can compile before a just-written Edit lands or skip compiling entirely (refresh_triggered false); confirm edits are live via DLL mtime, a new UTF-16 literal, or the live method's IL

## Editor & play mode traps

- [Play mode needs main scene](memories/playmode-needs-main-scene.md) — entering play mode hangs forever unless Assets/Scenes/main.unity is the active scene; check editor_state.active_scene first
- [No external edits to open Unity scenes](memories/no-external-edits-to-open-unity-scenes.md) — Write/Edit on an open .unity/.prefab raises a modal reload dialog that blocks the main thread and hangs the MCP bridge; edit via SerializedObject + SaveScene instead
- [Unity keyword-remap shader crash](memories/unity-keyword-remap-shader-crash.md) — known Unity engine bug crashing import worker on ParticlesUnlit fallback keyword remap
- [wsay voice notifications](memories/wsay-voice-notifications.md) — global hooks speak via wsay when Claude finishes (Stop) or needs input (Notification); don't disable

## ECS / Burst / baking

- [Stale Burst after merge](memories/stale-burst-after-merge.md) — post-merge Burst-job NREs (managed passes) = STALE Burst native code from changed job struct layouts, not a source bug; force a fresh Burst recompile and re-run twice
- [FFSystems/Player namespace collision](memories/ffsystems-player-namespace-collision.md) — systems in FFSystems/Player/ MUST use namespace `FFSystems.Players` (plural); `FFSystems.Player` collides with the Player component type and breaks all of FFSystems
- [ItemEntities baking pipeline](memories/itementities-baking-pipeline.md) — Resources/ItemEntities/*.prefab bake via EntityPrefabContainerBaker; author companion entities with CreateAdditionalEntity(ManualOverride) → in LinkedEntityGroup, remapped on Instantiate
- [ECS runtime material unload gotcha](memories/ecs-runtime-material-unload-gotcha.md) — runtime new Material() in a RenderMeshArray needs HideFlags.HideAndDontSave or UnloadUnusedAssets nulls it (BRG MaterialID <null> error)
- [Remote-player presentation position bug](memories/remote-player-presentation-position-bug.md) — FIXED & verified: host ship renders on client smoothly; the 3-part fix (Apply Option A + exclude remotes from LinearMotionSystem + per-frame presentation group)

## Modding

- [Mod ABI package pinning](memories/mod-abi-package-pinning.md) — why Entities/URP versions are pinned (entities 1.3.10 / URP 17 on Unity 6000.0.71f1)
- [ModLoader metadata inspection](memories/modloader-metadata-inspection.md) — mods inspected reflection-only (MetadataLoadContext) before Assembly.Load; which 3 plugin DLLs, the 4 polyfills to skip, and the FFCore.Unity namespace-shadowing gotcha (use global::Unity.Entities)

## Maintaining this skill

New durable lessons go here (one file in `memories/`, one index line above), committed to the
final-factory-agents repo — NOT to the per-worktree `~/.claude/projects/*/memory/` dirs, which
are machine-local and do not propagate.
