---
description: A script recompile that fires while the editor is in play mode tears the ECS world down and per-frame NREs grow Logs/sandbox-editor.log to GBs (w4360: 2.9 GB); refresh before play, or set ScriptCompilationDuringPlay to stop playing first, and restore it after.
---

# A recompile during play mode floods the editor log (w4360, 2026-11-16)

On m5/slot2 a `refresh_unity` (with an edited `.cs`) landed while LifeSave was in play mode. Unity recompiled in
play mode, the domain reload tore the ECS world down, and every frame afterwards threw NullReferenceExceptions from
systems and MonoBehaviours. `Logs/sandbox-editor.log` reached 2.9 GB before it was noticed.

How to apply:
- Run `refresh_unity` (compile) and wait for the reload BEFORE entering play mode; never edit and refresh mid-session.
- If a run must survive edits, set `EditorPrefs.SetInt("ScriptCompilationDuringPlay", 1)` (1 = recompile after
  play mode stops, 2 = stop playing and recompile) for the run, and restore the old value afterwards.
- A log already flooded: stop play mode, then truncate it (`: > Logs/sandbox-editor.log`), never delete it while the
  editor holds it.

# StationWarnings are computed only near the camera

`GridWarningCheckerSystem` (game repo `Assets/Scripts/FFSystems/StationGrid/GridWarningCheckerSystem.cs:572-585`)
fills `StationWarnings` / `ActiveWarning` only for player-placed entities within 600 units of
`GameMetaState.CameraPosition`. A loaded save read from far away shows no warning on any building, which looks like
"the warning never fires". Move the player and camera there first (`ffauto:player.setposition|x|z`,
`ffauto:camera.focus|x|y|z`), let a few frames run, then read them.
