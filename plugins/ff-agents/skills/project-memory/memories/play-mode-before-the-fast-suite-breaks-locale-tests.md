---
description: Entering play mode in an editor session and then running FFEditorTests fails LocalOnlyCheatRefusalTest (3 tests) with "SelectedLocale is null. Database could not get table." Run the suite in a fresh editor.
---

# Play mode before the fast suite fails three locale-dependent tests (w169, 2026-10-01)

After one play-mode session in the sandbox editor (entered and stopped through the bridge), the fast suite
failed `Tests.Multiplayer.LocalOnlyCheatRefusalTest.DestroyAllEnemiesIsRefusedInMultiplayer`,
`FreeBuildingsIsRefusedInMultiplayer` and `SetConstructionStageIsRefusedInMultiplayer` with
`Unhandled log message: '[Error] System.Exception: SelectedLocale is null. Database could not get table.'`.
The same commit in a restarted editor: 6,460 run, 0 failed.

Do the play-mode check and the suite in separate editor sessions (`mcp__sandbox__unity restart` between
them), suite first when only one is needed. Do not report these three as regressions without the
fresh-editor re-run.
