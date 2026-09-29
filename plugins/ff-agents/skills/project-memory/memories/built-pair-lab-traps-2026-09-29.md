---
name: built-pair-lab-traps-2026-09-29
description: "Headless 3-peer soak lab on one Windows box (sandbox mp-r2, 2026-09-29): movement.goto takes WORLD units, -ffAutomationReclaimIdentity per CLI client, config-file audit peer requirements, junctioned per-peer folders, PostConnectDelayMs is the dwell, and long builds from execute_code: use a one-shot EditorApplication.update (a synchronous body timed out and was replayed 6x)."
---

# Headless 3-peer soak lab traps (2026-09-29)

- **`ffauto:movement.goto x|z` is in WORLD units**, while `observe.state` reports `tile` = world/10
  and its `enemies|x|z|r` / `nearby` scopes take TILES. A camp at tile (-611,-472) is
  `movement.goto|-6110|-4720`; passing tiles flies ~10x too short and the "fight" never happens.
- **Two CLI clients from one build share `reclaim-identity-automation-client.txt`** (keyed by role):
  give each `-ffAutomationReclaimIdentity <name>`. A `.ff-local-automation.json` peer cannot set it,
  so mix: config for the audited peers, CLI + ReclaimIdentity for the rest.
- **A config-file audit peer is rejected** (`audit-config-invalid`) without `AuditSaveSha256`
  (64 hex), a 40-char `AuditSourceRevision`, and a non-zero `AuditDwellReleaseTimeoutSeconds`
  (0 = unlimited is only legal with `verification-v3-continuous`). The config is read from the
  parent of `Application.dataPath`, so per-peer folders can share one 2.2 GB build: copy the exe
  and DLLs, junction `finalfactory_Data`, `MonoBleedingEdge`, `D3D12`, `AgentKit`. Reports are
  only written when the dwell gate is released, not when the process is killed.
- **`-ffAutomationPostConnectDelayMs` is the dwell length.** Leave it at the default and the harness
  logs `session-ended` after a second (the player keeps running); set 36000000 for a live soak.
- **Long editor work from `execute_code`:** a synchronous `BuildPipeline.BuildPlayer` body timed out
  on the bridge and the call was REPLAYED, building the player 6 times back to back (this corrects
  the 09-21 advice). Register a one-shot `EditorApplication.update` handler that unregisters itself
  and builds, return at once, and poll the Editor log for a start/result marker (211 s build, ran on
  the first tick even unfocused). `delayCall` still did not fire on the unfocused editor.
