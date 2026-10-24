---
description: A Steam pair run's client leg on a Windows built player - topmost clicks through the title menu, ff-leftovers ends Steam, player_slots wants the exe, and how long to suspend and how far apart for a reconnect round.
---

# Steam pair run, client leg: menu clicks, Steam, and reconnect rounds

From w2056 (pair run for w1958's PR #2400, a rejoin reclaiming its own character by Steam account; client leg on
lothdesktop, host on BEAST, 2026-10-24).

## Getting a built player into a Steam lobby

- **The agent control channel refuses commands at the title menu**, so Multiplayer > Browse Games > the lobby row > Play
  are OS clicks. On a machine where other sandboxes' Unity editors are open, a click at the player's coordinates landed
  on another editor: they cover the player window and take focus back. What worked: `SetWindowPos(hwnd, HWND_TOPMOST,
  ...)`, then a key press of Alt (keybd_event VK_MENU down/up) so Windows lets `SetForegroundWindow` through, then the
  click. Check with `WindowFromPoint` which window owns the point before clicking. Fractions of the client area at
  1920x1080 (measured, this build): Multiplayer (0.176, 0.501), Browse Games (0.494, 0.624), first lobby row
  (0.39, 0.40), Play (0.605, 0.751); "Session Ended" Back (0.386, 0.583).
- **`player_slots.py launch` wants the exe path** (`.../player/finalfactory.exe`); given the build folder it failed with
  WinError 5 (access denied, it tried to run the folder).
- **`ff-leftovers end` ends a Steam client your session started**, with its webhelpers. Mid-run, that drops you out of
  the lobby: restart it with `Start-Process "c:/games/steam/steam.exe" -ArgumentList "-silent"` and sweep only at the
  end.

## Suspending the client for a reconnect round

Measured with NtSuspendProcess / NtResumeProcess on the client player (build f1a4d15f):

- **Under about 10.75 s nothing reconnects.** The client watchdog (5.2 s) can only trip after the process resumes, and
  by then the host has not dropped it, so the client just catches up (7 s round: host "caught up after 5.9 s"). From
  about 10.75 s the host evicts it (`FlowControl:HardDrift`) and the rejoin takes the ordinary path, so a suspension
  hardly ever hits the ghost-supersession race (the ghost still live when the rejoin arrives). The one race hit came
  from a real relay outage, not a suspension.
- **Space rounds at least 60 s apart.** The reconnect attempt counter resets only after 60 s of stable play
  (`ReconnectEngine.cs:487-490`, `ReconnectProbationSeconds = 60.0` at `DesyncRecovery.cs:217`), and the fourth attempt
  inside that window ends the session for good (`ReconnectEngine.cs:424-430`). Rounds 30-45 s apart logged
  ReconnectAttempt(1), (2), (3).
