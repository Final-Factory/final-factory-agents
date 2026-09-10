---
name: drive-interactive-verification
description: "Standing authorization to launch, play, inspect, and recover Final Factory during development"
metadata:
  node_type: memory
  type: feedback
---

# Execute the authorized playtest

Ben explicitly authorized autonomous Final Factory development and live multiplayer testing across his three machines, including launching the game, playing through real inputs, screenshots and visual inspection, tests, builds, and recovery of positively identified project-owned processes. He repeated this on 2026-09-10 after a redundant app-access approval interrupted an overnight run. Carry that authorization across turns and agents. Do not ask whether you may use Final Factory, launch a test player, inspect its window, or run the next routine development step.

Use `ff-agents:playtest`, `ff-agents:drive-game`, `ff-agents:editor-ops`, and `ff-agents:determinism-audit`. Built-player AgentControl provides real inputs and composited screenshots without requiring general desktop-app access. Inspect the resulting images; a screenshot file alone is not visual verification.

Distinguish task authorization from platform enforcement. Existing authorization does not disable macOS permissions or a host-managed approval classifier. Prefer the already available project-specific control channel. If a platform blocks one route, continue independent work and try another authorized route; do not ask Ben to reauthorize the task. Never claim that a skill update disables the platform classifier. Report an unavoidable platform blocker precisely, with the action and returned reason, only when it actually prevents further progress.

# Keep the run moving

A status question is not a request to stop. When Ben says to stop asking permission while continuing development, stop the redundant questions and continue the task. Honor an unambiguous instruction to stop work.

Own every launched job through completion, failure, or scoped cleanup. Use bounded external calls and process timeouts, retain job IDs, and monitor phase transitions and terminal outcomes. Do not let an optional desktop inspection hold the whole multiplayer run: prefer AgentControl screenshots, and give a peer-owning agent a finite no-progress deadline and cleanup authority before starting. A thread heartbeat cannot guarantee progress while its foreground tool call is blocked. After a timeout preserve evidence, diagnose, and retry or select the next useful task. Never count idle waiting or a host-only run as multiplayer verification.

Credential entry, unavailable hardware, and decisions outside the authorized task can still require user input. Preserve unrelated processes and user data, and obey release branch governance. These boundaries are not reasons to invent approval steps for normal gameplay testing.

## Preserve both live audit reports before cleanup

On a multiplayer failure, run `ffauto:audit.write` through each peer's development AgentControl
session, then verify, copy and hash BOTH returned report files before stopping either process.
The command wraps `LocalMultiplayerAutomationCommandRunner.ExecuteAuditWrite` →
`NetworkDeterminismAudit.WriteReport`; it publishes current rows without resetting capture.
Do this at useful milestones too. Normal dwell/teardown gates can postpone automatic publication,
so a RED run is not permission to terminate a peer with its only evidence still in memory.
Recovery itself retains audit rows; do not claim recovery erased them without evidence. With a
capture policy, the report path uses run/leg/role identity and ignores the optional label; copy
milestone reports to distinct artifact filenames. Explicitly report missing peer evidence and
capture overflow/caps instead of claiming a paired comparison from one log.
