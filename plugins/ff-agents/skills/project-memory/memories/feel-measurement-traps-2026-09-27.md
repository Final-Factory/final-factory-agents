---
name: feel-measurement-traps-2026-09-27
description: "Measuring game feel on built Mac players (2026-09-27 smoothness investigation): a locked screen throttles ScreenCaptureKit to 30 Hz for the game window and system-wide CGEvent keys type into the lock screen; relative player path flags resolve against the build folder; single-player at 16 UPS isolates tick-rate effects from the network; pause makes controller dt 0; automation hosts rotate Ben's autosaves and flush his desync upload queue; a back-to-back batch dev build can fail in the Entities ILPP; the in-game menu's Escape is legacy input."
metadata:
  type: project
---

# Feel measurement traps, 2026-09-27 (smoothness investigation)

Background: `docs/Smoothness-Investigation.md` in the game repo; tools in `scripts/feel/`
(`FeelProbe` via `-ffFeelProbe`, `ffcap.swift`, the analyzers, `README.md`).

- **A locked Mac is only half a lab.** The game renders normally behind the lock screen (vsync still
  paces it), but ScreenCaptureKit gets the occluded window at about 30 Hz (a content change every
  ~33 ms while the game ran at 60 fps), so photon and present-cadence measurements are impossible.
  A system-wide `CGEvent.post(tap:)` goes to the lock screen's password field. Post keys to the game
  only (`CGEvent.postToPid`, `ffcap --to-pid`) or inject them in the game (`-ffFeelKeys`, Input System
  state events). Check `CGSessionCopyCurrentDictionary()["CGSSessionScreenIsLocked"]` before a capture
  run. Over ssh the M3 also refuses screen capture and event posting (TCC), and its display sleeps:
  `caffeinate -u -d -i -t <seconds>` wakes it.
- **Relative path flags land in the build folder.** A Mac player started with
  `-logFile runs/x/Player.log` (or `-ffFeelProbe runs/x/probe.csv`) writes next to the `.app`, not in
  the shell's cwd. Pass absolute paths, especially in ssh one-liners.
- **Isolate the tick rate without a network:** single-player at 16 UPS (`-ffFeelUps 16`, or the dev
  console's `setRateLimit 16`). It reproduced the multiplayer presentation stutter exactly (heartbeat
  frames cost about twice the others, and Unity's delta is the previous frame's duration), which
  showed the cause was the tick rate, not the network. Judge smoothness by the probe's on-screen
  speed (the dt a frame used divided by its own duration, i.e. the next frame's delta), not by
  frame-time percentiles.
- **Pause makes dt zero.** `GameplayManager.cs:26` sets `Time.timeScale = 0` while paused
  (single-player, or a host with no remote peers), so every controller-group delta is 0 on paused
  frames. Anything that learns from frame time (the frame pacer) must skip zeros, or its estimates
  collapse and motion stutters for seconds after resume.
- **Automation hosts touch Ben's game data.** A host that lives past 5 minutes autosaves into his
  `saves/_autosave_N.zip` slots (the index is in PlayerPrefs), and the game's upload queue sends any
  of his pending desync reports. Before lab runs on m5/m3, copy `saves/_autosave_*` and
  `defaults export com.Never-Games.finalfactory` into the backup folder; restore both afterwards
  (`defaults import`). Saved display prefs also override launch-size flags (see
  visual-capture-native-resolution-and-review).
- **Back-to-back batch builds.** A development build started right after a release build of the same
  Library failed with an Entities ILPP NullReferenceException on `KNN.dll` plus a licensing handshake
  error; the same build 30 s later succeeded. A release build takes 2 to 5 minutes on the M5, and
  `lib_burst_generated.bundle` appears in `PlugIns/` only when it has finished.
- **Escape is legacy input.** The in-game menu opens on `UI.InputHelper.GetKeyDown(KeyCode.Escape)`
  (`UiController.cs`), so an Input System state event does not open it; use
  `InputHelper.InjectKeyDown`. No ffauto command opens that menu.
- **Editor churn.** Starting the editor on the M5 sometimes flips
  `Assets/Plugins/FMOD/platforms/mac/lib/fmodstudio*.bundle.meta` OSXUniversal `enabled: 1` to `0`.
  It is not a real change; do not commit it (batch builds still shipped `fmodstudio.bundle`).
