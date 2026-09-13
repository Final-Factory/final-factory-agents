---
name: built-player-native-cua-input
description: "Native CUA input lesson from the 2026-09-13 Mac built-player audit: target the exact app path, raise its current AX window, and prove each input effect with fresh AgentControl screenshots."
---

# Built-player native CUA input (2026-09-13, 069 lane r17)

The Mac audit player was `/tmp/ff069-codex-20260913-1819/player/finalfactory.app`. There were multiple copies with the same bundle ID, so select the player with native `mcp__cua_repl` `getApp` using that exact app path. Re-query `getAXState` before every action: window indices are not stable.

Orca `press-key` returned `window_not_focused`; restore, `osascript` activation, and title-clicking did not cure it. The exact-app CUA path worked: `getAXState` exposed window `0` with `SecondaryActionRaise`; `performSecondaryAction(0, "Raise")`, then `pressKey("r")`, delivered a held-inserter rotation. A fresh dedicated AgentControl screenshot showed the green preview, then a real click built eastward and the tutorial card completed. After placement, `pressKey("escape")` through the same exact-app handle cleared the UI/hand before the next inventory pick.

Use only runtime-documented CUA APIs. Keep screenshot evidence separate from the desktop-control route, and inspect a fresh green-preview screenshot before treating an input as delivered. In one attempt, several rapid `R` calls produced only one observed rotation. No cause was diagnosed: split repeated inputs across game frames and inspect each result.

This is real player input, not a deterministic-injection result. `RotatorAction` reads the Rotate input (`RotatorAction.cs:24-30`); held-blueprint rotation is local presentation (`RotatorAction.cs:32-43`), while rotating a placed structure uses the network operation (`RotatorAction.cs:46-60`). `ffauto:rotate.abs` is a placed-structure network route (`LocalMultiplayerAutomationCommandRunner.cs:4666-4694`). `ffauto:rotate.local` deliberately queues a peer-local RED-baseline rotation and is forbidden outside that test (`LocalMultiplayerAutomationCommandRunner.cs:4697-4716`). This r17 evidence, including FF9 artifacts under `/private/tmp/ff069-codex-20260913-1819` on M5, makes no engine-fix claim.
