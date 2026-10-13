---
description: Entering play mode in an editor session and then running FFEditorTests gives false failures (w169 three SelectedLocale-is-null locale tests; w918 31 UI-test NullReferenceExceptions). Run the suite in a fresh editor.
---

# Play mode before the fast suite fails three locale-dependent tests (w169, 2026-10-01)

After one play-mode session in the sandbox editor (entered and stopped through the bridge), the fast suite
failed `Tests.Multiplayer.LocalOnlyCheatRefusalTest.DestroyAllEnemiesIsRefusedInMultiplayer`,
`FreeBuildingsIsRefusedInMultiplayer` and `SetConstructionStageIsRefusedInMultiplayer` with
`Unhandled log message: '[Error] System.Exception: SelectedLocale is null. Database could not get table.'`.
The same commit in a restarted editor: 6,460 run, 0 failed.

**Again in w918 (2026-10-13, lothdesktop slot3), bigger:** after a play session that started a tutorial game by
reflection and Step-pumped it, the full fast suite reported 31 failures, every one a NullReferenceException in a UI
test (`BlueprintPanelPointerDragTest` x6, `StationStripSizesTest`, `StationButtonsCompactTest`, `InGameExitGameTest`,
`NewGameTutorialToggleTest`, `HoverPlaceableStatsDirectionTest`, `SelectionColumnPanelsTests`). After
`mcp__machine__unity restart` those eight classes ran 59/59 green. Which tests break depends on what the session
touched, so treat any cluster after a play session as this until a fresh editor says otherwise.

Do the play-mode check and the suite in separate editor sessions (`mcp__sandbox__unity restart` between
them), suite first when only one is needed. Do not report these three as regressions without the
fresh-editor re-run.
