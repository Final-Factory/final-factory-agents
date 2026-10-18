---
name: test-the-mods-restart-and-steam-on-a-shared-machine
description: How w1459 measured #1744's "Switch mods and restart" relaunch and the Steam overlay on BEAST - why a launch through Steam fails there, how to reach the mods dialog with a private mods folder, the launch arguments a relaunch keeps, and two traps in SaveCompatibilityLiveLoadTest runs.
metadata:
  type: feedback
---

**From w1459 (2026-10-18, beast, master dev player ab91fc2ed, 1.0.0.0).**

**A launch through Steam fails on a shared machine.**
- `steam.exe -applaunch 1383150 <args>` failed with `LaunchApp failed with AppError_16` after `WaitingPrevProcess`
  (Steam's `logs/console_log.txt`). Steam counts every slot-pool player on the machine as Final Factory running,
  because a slot player calls SteamAPI_Init with the app id. `logs/gameprocess_log.txt` lists them: "AppID 1383150
  adding PID ... as a tracked process".
- Once no player ran, the launch stopped at `waiting for user response to SynchronizingCloud "cloudconflict"`. There
  were 23 files in conflict in `logs/cloud_log.txt`: the shared saves folder's `_autosave_*` and `_automation_autosave_*`
  saves and `UserData/settings/settings.json`, each with different local and remote SHAs, written by agent players on
  several machines on one Steam account.
- Which copy to keep is the account owner's call. Never answer that dialog. Say so in your report with
  `waiting_on_person`.

**A slot player gets the Steam overlay without Steam launching it.**
- The overlay renderer was injected into a slot-launched player: `logs/gameoverlay_renderer.txt` showed "Process ID: <pid>"
  and `GameID = 1383150, OverlayGameID = 1383150`. That file is rewritten for each process it hooks, the crash handler
  child included, so read it right after the launch.
- What a relaunch keeps is measurable without a Steam launch:
  - the relaunched process's modules (`(Get-Process -Id <pid>).Modules`: `gameoverlayrenderer64.dll`, `steamclient64.dll`);
  - its "Connected to Steam as user" log line;
  - Steam tracking its PID, and the PowerShell relaunch helper's PID, in `gameprocess_log.txt`.
- Not measured this way: the overlay drawing on Shift+Tab. That needs OS input, which a shared machine forbids.

**Reaching "Switch mods and restart" with a player you drive.**
- `-ffModsPath <dir>` gives the player its own mods folder (w1252), and the relaunch keeps the argument.
- BEAST's subscribed Workshop code mods (`steamapps/workshop/content/1383150/*`: Calculator, AttackTracker and others) are
  built for 0.18, and the loader refuses them (`IncompatibleGameVersion`). For a test, copy one into your folder and set
  `GameVersion=1.0.0.0` in the copy's `manifest.properties`. Calculator then loads.
- The dialog only offers the switch for a save whose mod record differs (`SaveModsCheck.CanSwitch`). A save made by a
  player with an empty mods folder records "no mods", and loading it with Calculator running asks.
- `ui.loadgame|<save>` confirms every dialog the Load press opens, so it presses "Switch mods and restart" by itself.
  `ui.loadgame|<save>|select` only picks the row, and the channel then refuses every command while the Esc menu pauses
  the game. A still of the dialog itself needs another route.
- **The relaunch keeps every launch argument except `-ffLoadSave` and `+connect_lobby`**
  (`GameRelauncher.BuildRelaunchArguments`).
  - A test launch with `-ffSoloNewGame` relaunches with it, and the nightly new-game bootstrap then races the pending
    load in the same frame: "Could Not Load Save: ArgumentException: An item with the same key has already been added".
    That is a test artifact.
  - Get into the game with `-ffLoadSave <save>` instead. `PendingSaveLoad` opens it with no mods check, and the relaunch
    strips it.
- A relaunched player writes to the same `-logFile`. Copy the first process's log before you press Load.

**SaveCompatibilityLiveLoadTest in a sandbox editor.**
- After a failed run, a second run of a fixture in the same editor session fails within 1 s:
  `GetSingleton<GameMetaState>() requires that exactly one entity exists`. Restart the editor, or recompile, between runs.
- The machine-wide F7 setting (`HideFlyingStations` in `UserData/settings/settings.json`, which every editor and player on
  the machine shares) makes the LifeAsTwoMegaWave load throw `The previously scheduled job
  FlyingStationVisibilitySystem:SetFlyingBeltItemsRenderingJob writes to the ComponentLookup<MaterialMeshInfo>`. That
  fails the test before its own checks run (3 of 3 runs with F7 on).
- The editor keeps the settings in memory and writes them back. To change one for a run, use `execute_code`:
  `GameSettings.SetInt(...)` then `GameSettings.Save()`. Snapshot first with the game repo's `scripts/game_data.py`, and
  restore that snapshot after, not a value you assume: another worker had changed it in between.

Related: [[bench-runs-on-a-shared-machine]], [[a-workflow-file-push-needs-the-workflow-scope]].
