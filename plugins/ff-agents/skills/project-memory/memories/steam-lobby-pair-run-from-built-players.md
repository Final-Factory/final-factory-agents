# A real Steam-lobby pair run from built players (w2056, 2026-10-24)

A fix that depends on Steam identity (the host matches a joiner by its Steam-verified account, e.g.
`ReclaimSupersession.TryFindAccountGhost`, PR #2400) needs a real Steam lobby on two machines under two
different Steam accounts. The `-ffAutomation*` harness can't give you one.

## The harness hosts only on localhost or Unity Relay

`LocalMultiplayerAutomationBootstrap.cs` (`CreateLocalMultiplayerLobbyParameters`, ~line 951) builds
non-Steam lobby parameters. A Steam lobby comes only from the title menu: Multiplayer → Host new game
(or Host saved game), then `NetworkedGameManager.HostNewMultiplayerGame`, then `SteamLobbyStartup.CreateLobby`.
The lobby id is logged nowhere, so the client joins by name: Multiplayer → Browse Games. Rename the
lobby in Game Settings ("w2056 slims host") so it is unique in the public list.

## Driving the title menu of a built player on Windows

- Launch through `player_slots.py launch ... -- -screen-fullscreen 0 -screen-width 1600 -screen-height 900
  -logFile <tmp> -ffAgentControl true -ffAgentControlDev true`. `GET /v1/screenshot` works at the title
  screen (`scripts/agent/peer.py <slot-substring> shot client <png>`); `/v1/command` answers 409 until a world runs.
- Agent control has no title-menu clicks. Use OS mouse input from PowerShell, in this order:
  `SetProcessDPIAware`; `ClientToScreen` on game-client coordinates; `ShowWindow(h,9)`;
  `SetWindowPos(h, HWND_TOPMOST=-1, 0,0,0,0, 3)`; tap Alt (`keybd_event 0x12` down/up);
  `SetForegroundWindow`; `SetCursorPos`; `mouse_event` 2 then 4. Without topmost + Alt the click lands
  on whatever window is in front. `SendKeys` `^a` plus the text edits the lobby name.
- Game-client coordinates at 1600x900: Multiplayer (230,451); Host new game (788,454); Host saved
  game (788,513); Browse Games (788,572); New Game dialog Tutorial toggle (692,432), Disable Enemies
  (692,484), Continue (1027,700); Game Settings name field (840,406), Play (1000,619) for a new game,
  (1000,634) for a saved game. The dialog remembers the last settings, so take a screenshot before
  you toggle anything.
- Seeing `Steam returned no lobby after creation completed.` (`SteamLobbyStartup.cs:144`) about 11 s
  after Play, while the log still says "Connected to Steam as user X", means the desktop Steam client
  is signed out (its window title is "Refresh Sign In"). Only a person can sign it back in: use
  `waiting_on_person`. Check the title first with
  `Get-Process steamwebhelper | ? MainWindowTitle`; it should read "Steam".

## Hitting the ghost-supersession race

The client watchdog trips after 5 s with nothing applied (`ReconnectThresholds.WatchdogSeconds`). The
host closes a stalled client after about 10.75 s (`FlowControl:HardDrift`). Suspending the client
process can't reach the race:
- Under ~10.75 s, the frozen client never trips its watchdog. It resumes into a live stream and only
  catches up (7 s: "caught up after 5.9 s", no reconnect).
- Over that, the host has already closed the ghost before the rejoin, so you get the ordinary
  `ReclaimBySteamId` path (10.5, 13, 15, 16 and 19 s all did).

The race (`[Reconnect] Superseded(ghost=N) by client M`) came on its own during a Unity Relay outage.
The client's attempt 1 timed out after 10 s, and attempt 2 arrived while the ghost was still live.
To produce it on purpose, the connection must drop without freezing the client: block its network,
not its process.

## Space reconnect rounds at least 60 s apart

The client's attempt counter resets only after the 60 s probation (`ReconnectEngine.cs:487-490`,
`DesyncRecovery.cs:217` `ReconnectProbationSeconds`). Rounds 30-45 s apart share one budget of 4
attempts, and a fifth reconnect inside that window ends the session as terminal.

## Disk

While you wait on a person, your temp folder's builds, helper scripts and `game_data.py snapshot`s can be
swept. Rebuild (with a build cache this is quick), keep helper scripts reproducible, and expect a settings
snapshot from before the wait to be gone.
