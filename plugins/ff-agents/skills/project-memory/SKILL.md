---
name: project-memory
description: Accumulated Final Factory project memory — standing user feedback plus hard-won Unity, Burst/ECS, baking, modding, and play-mode lessons. Consult at the start and end of every Final Factory repository development task so fixture-selection and the required @lothsahn Discord completion notification are not missed; also consult BEFORE debugging the MCP bridge, running tests, entering play mode, editing open scenes, diagnosing Burst NREs after a merge, or working on mod loading.
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
- [Watch logs without full scans](memories/watch-logs-without-full-scans.md) — never poll a big log by re-scanning it each tick (the watcher falls behind and stalls silently); query once directly first, then tail/byte-offset only
- [Skill docs go decision-first](memories/skill-docs-decision-first.md) — when a doc fails to stop a mistake, restructure it: falsifying test first, look-alike traps contrastive, recipes to a companion file
- [Choose the smallest representative playtest fixture](memories/feedback-focused-fixtures-before-meltcpu.md) — default to Wittle Base, FlatMap, or another focused 16-UPS fixture for behavior/visual/feel tests; reserve MeltCPU for explicit worst-case scale and performance questions
- [Notify Lothsahn when a repository task finishes](memories/feedback-discord-completion-notify-lothsahn.md) — after successful implementation and verification, post one extremely brief `@lothsahn` FYI in Discord `#dev-chat`, in PLAIN ENGLISH saying what behavior changed (no hashes/system names/audit stats); batch related substeps into one completion ping
- [Publish harness changes/lessons to ff-agents proactively](memories/feedback-publish-harness-changes-to-ff-agents.md) — whenever a session changes shared harness behavior or learns a durable, reusable lesson, run the publish-skills workflow in that SAME session without being asked; batch the session's lessons into one version bump; report a blocked publish explicitly

## Unity MCP bridge

- [Unity MCP server](memories/unity-mcp-server.md) — Coplay MCP-for-Unity via stdio (multi-instance safe); Claude spawns server, editor must be set to Stdio transport in Window>MCP for Unity; tools load only at Claude restart
- [Unity MCP resource URIs](memories/unity-mcp-resource-uris.md) — resource URIs use slashes and differ from the `name` field; editor readiness is `mcpforunity://editor/state` NOT `editor_state`; read the `uri` field, don't build from name
- [UnityMCP per-project config](memories/unitymcp-per-project-config.md) — the Unity bridge tools require a per-project UnityMCP server in ~/.claude.json (claude mcp add + restart)
- [Verify compile via DLL string check](memories/verify-compile-dll-string-check.md) — refresh_unity can compile before a just-written Edit lands or skip compiling entirely (refresh_triggered false); confirm edits are live via DLL mtime, a new UTF-16 literal, or the live method's IL
- [Bridge TCP fallback facts](memories/bridge-tcp-fallback.md) — policy says bridge-down = stop-and-notify (use the `unity` CLI for diagnostics), but the editor-driving facts hold: Roslyn execute_code works on Windows, UI clickable via reflection, read_console returns from the START of the buffer, LoadGame by name
- [Unity Editor.log gotchas](memories/unity-editor-log-gotchas.md) — line numbers unreliable (binary content), slice with `awk` after a dropped marker, `grep -a`, map bridge port→PID to find the right editor, saturated main thread freezes the bridge without hanging the editor

## Editor & play mode traps

- [Play mode needs main scene](memories/playmode-needs-main-scene.md) — entering play mode hangs forever unless Assets/Scenes/main.unity is the active scene; check editor_state.active_scene first
- [No external edits to open Unity scenes](memories/no-external-edits-to-open-unity-scenes.md) — Write/Edit on an open .unity/.prefab raises a modal reload dialog that blocks the main thread and hangs the MCP bridge; edit via SerializedObject + SaveScene instead
- [Unity keyword-remap shader crash](memories/unity-keyword-remap-shader-crash.md) — known Unity engine bug crashing import worker on ParticlesUnlit fallback keyword remap
- [wsay voice notifications](memories/wsay-voice-notifications.md) — global hooks speak via wsay when Claude finishes (Stop) or needs input (Notification); don't disable
- [Profiling ECS + fork pin bumps](memories/knn-profiling-and-fork-pin-gotchas.md) — ProfilerRecorder never samples system markers (use ProfilerDriver.enabled + GetRawFrameDataView); clone Packages/ can be a real dir: copy manifests + Client.Resolve() on the clone, verify PackageCache sha + fresh assembly mtime before trusting any run

## ECS / Burst / baking

- [Stale Burst after merge](memories/stale-burst-after-merge.md) — check `EnableBurstCompilation` before EVERY test run (Burst off = a green suite that never exercised the Burst compile, plus ~10x slower); Burst compiles ASYNCHRONOUSLY: a clean console right after `refresh_unity` proves nothing, wait for `BurstLoader.BurstProgressId` to go idle before reading results; post-merge Burst NREs or BC1054s (even ones blaming files that never mention the type) = stale `Library/BurstCache/JIT`, not a source bug
- [Test-assembly systems need [DisableAutoCreation]](memories/test-assembly-systems-need-disableautocreation.md) — unmarked SystemBase/ISystem in Assets/Tests auto-creates into live play mode (static entities accumulate render-only drift the fingerprints can't see); always mark; diff LtW vs LocalTransform to detect
- [FFSystems/Player namespace collision](memories/ffsystems-player-namespace-collision.md) — systems in FFSystems/Player/ MUST use namespace `FFSystems.Players` (plural); `FFSystems.Player` collides with the Player component type and breaks all of FFSystems
- [ItemEntities baking pipeline](memories/itementities-baking-pipeline.md) — Resources/ItemEntities/*.prefab bake via EntityPrefabContainerBaker; author companion entities with CreateAdditionalEntity(ManualOverride) → in LinkedEntityGroup, remapped on Instantiate
- [ECS runtime material unload gotcha](memories/ecs-runtime-material-unload-gotcha.md) — runtime new Material() in a RenderMeshArray needs HideFlags.HideAndDontSave or UnloadUnusedAssets nulls it (BRG MaterialID <null> error)
- [Remote-player presentation position bug](memories/remote-player-presentation-position-bug.md) — FIXED & verified: host ship renders on client smoothly; the 3-part fix (Apply Option A + exclude remotes from LinearMotionSystem + per-frame presentation group)
- [BlockAllocator budget crash](memories/blockallocator-budget-crash.md) — "Cannot exceed budget of 16777216": the two fixed 16MB allocators, what actually grows them (distinct-archetype count, NOT repeated identical CreateEntityQuery), and the save-load one-at-a-time AddComponent archetype explosion + ComponentTypeSet batching fix
- [Unscoped marker sweeps fork multiplayer](memories/unscoped-marker-sweeps-fork-multiplayer.md) — a query over "every entity with kind-marker X" mutates other peers' preview ghosts (4 instances on BlueprintItemMarker); scope by BlueprintGhostOwner IDENTITY (never timing), fail closed on a missing stamp, and check shared-hash queries for peer-local matches via BAKED components (grep the prefab, don't trust "structure-only")

## Localization

- [French percent = Arabic sign](memories/french-percent-arabic-sign.md) — Unity's Mono culture data gives fr `PercentSymbol` = U+066A ٪ (no font has the glyph); fixed by CultureSetup.cs, plus the Mono Clone()-shares-NumberFormatInfo gotcha
- [TextLocalization duplicate gotcha](memories/textlocalization-duplicate-gotcha.md) — TextLocalization caches live TMP text as its key, so duplicating it on a label (Checkbox prefabs already have it) locks that label to one language; never put it on proper-noun labels

## Gameplay diagnosis & live-test recipes

- [Unified 16 UPS smooth presentation](memories/project-unified-16ups-smooth-presentation.md) — feature 057 goal and current progress: player, belts, and projectiles smooth; next formal belt jam-stop checkpoint and Phase C movers
- [Player domain is already conventional](memories/player-domain-already-conventional.md) — the player replication/simulation boundary already matches the proposed split; presentation rate is the real issue, while combat remains the open domain decision
- [Cargo ship teleport diagnosis](memories/cargo-ship-teleport-diagnosis.md) — camera-gated presentation sync over ungated simulation = ghost-then-snap artifact (InserterRenderSystem); plus the live-probe/A-B methodology via execute_code (onBeforeRender probes, GravityForces mover, Error-Pause gotcha)
- [Mobile station merge bug](memories/mobile-station-merge-bug.md) — why stations merged on landing (overlap-only checks vs EntityMap, flying stations absent from the map); fixed via landing-footprint claims (TryClaimLandingZone, landed on master); bug-report saves load by filename via SaveGameManager.LoadGame
- [Black hole visual test recipe](memories/blackhole-visual-test-recipe.md) — "BlackHole" save + teleport coords, 200u death radius, swirl = rotating skybox (the shader never animates), fixed-res Game view screenshot workaround

## Modding

- [Mod ABI package pinning](memories/mod-abi-package-pinning.md) — why Entities/URP versions are pinned (entities 1.3.10 / URP 17 on Unity 6000.0.71f1)
- [ModLoader metadata inspection](memories/modloader-metadata-inspection.md) — mods inspected reflection-only (MetadataLoadContext) before Assembly.Load; which 3 plugin DLLs, the 4 polyfills to skip, and the FFCore.Unity namespace-shadowing gotcha (use global::Unity.Entities)

## Maintaining this skill

New durable lessons go here (one file in `memories/`, one index line above), committed to the
final-factory-agents repo — NOT to the per-worktree `~/.claude/projects/*/memory/` dirs, which
are machine-local and do not propagate.
