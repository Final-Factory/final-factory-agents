# Drive a built player's title and pause menus with real input (w2730)

**The fact.** A built player started with `-ffAgentControl true` serves its agent channel at the title menu, but every
ffauto command there answers `{"error": "state_not_playable", "detail": "commands need a running game; the game is
'menu'"}` (measured: beast, v1.0.0.29 dev player of bc5e74aa80, 2026-11-04). `peer.py <mark> shot client <png>`
(GET `/v1/screenshot`) still works at the menu, so the loop is: real click, then a screenshot to read the result.

**How to apply** (Windows, an unlocked desktop session: the Steam lobby check of w2730 needed it):

- Launch from the slot pool with `-ffAgentControl true -ffAutomationLabel <mark>` (peer.py finds the player by that mark;
  with no `-ffAutomationRole Host` it calls it `client`) and `-screen-fullscreen 0`.
- A PowerShell helper on the player's `MainWindowHandle`: `ShowWindow(h, 9)`, an Alt key tap (`keybd_event 0x12` down,
  up) so `SetForegroundWindow` is allowed from a background process, then `GetClientRect` + `ClientToScreen` to turn a
  point read off the 1600x900 screenshot into screen pixels (scale by client size / 1600x900: the window was 914x514),
  `SetCursorPos` + `mouse_event` (2 down, 4 up). Type with `[System.Windows.Forms.SendKeys]::SendWait`, `^a` to select
  a field's old text first. The helper: `drive-a-built-players-menus-win.ps1` beside this file (`-procId <pid> -action click|type|key -x -y -text`).
- Paths that worked on 1.0.0.29: title Multiplayer > Host new game > New Game Continue > Game Settings (Game name,
  Game Password, Max Players, Public toggle) > Play; in game Esc > Load Game > a save > Load Game > "Load for
  everyone?" Load Game; Esc > Exit to Menu > Exit. Check the save's Version in the Load panel: pick one at or below
  the build.
