---
name: built-player-esc-menu-ui-tours-and-clips
description: In a built player the agent channel refuses every command while single-player is paused (the Esc menu) and post_key.py clicks never reach uGUI; drive Esc-menu screens (Load, Save) with a development player's Deck tour, and record UI clips with the tour's record step
metadata:
  type: feedback
---

w1316 (Load panel screenshots, beast, 2026-10-14), a release and a development bench player:

- **Paused = no commands.** With the Esc menu open a single-player game is paused, and the agent channel answers every
  `command` with `409 state_not_playable` ("the game is 'paused'"). Only `/v1/screenshot` still answers (`maxEdge`
  320..1920; `peer.py shot` asks for 1600, so its PNG is 1600 wide whatever the window).
- **Posted clicks do nothing.** `scripts/agent/post_key.py <pid> click:x:y` (WM_LBUTTONDOWN/UP) reached neither the
  Esc menu nor the Load panel (the project's Input System, `activeInputHandler: 2`); posted `esc` works (legacy
  `Input.GetKeyDown`), but two quick escapes may close only one layer.
- **What works:** a development player with a Deck tour: `-ffDeckTour <steps.json> -ffDeckTourOut <dir> -ffDeckTourQuit
  -ffDeckTourSize 1920x1080 -ffDeckTourUiScale 0.9` (1280x800 at 0.8 for the Deck), steps `{"press": "button_escape"}`,
  `{"click": "text:Load Game"}`, `{"click": "text:<save name>"}`, `{"shot": ...}` (still + census) and
  `{"record": "<name>", "seconds": 12}` (async: later steps run while it records; frames + `frames.txt` for ffmpeg
  concat, 33-41 fps there). `{"setup": "ffauto:game.save|claude_playtest_<x>"}` runs before the menu opens. Also
  `ffauto:ui.loadgame|<save>|select` (dev, w1316) opens Esc -> Load and picks the save without loading it, from a running
  game only.
- **Desktop clips fail on beast:** `record_clip --pid` got no ddagrab frame in 8 s, and gdigrab recorded another
  editor's "Importing assets" dialog over the player even after `SetWindowPos(HWND_TOPMOST)`. Use the tour's `record`
  step (the game's own frames), as [[beast-clip-capture-and-slot-launch-traps]] says for gameplay.
- **The record step can starve the game on biscuit (w1773, Linux):** a tour's `record` step held a 1920x1080 development
  player at about 1.4 fps, so a clip of a UI change showed nothing at real rate. Record from outside instead: wait for the
  `shot <name>:` line in `tour.log`, then `ffmpeg -f x11grab -framerate 60 -window_id <id from xwininfo -root -tree> -i :0 -t 12`
  (static ffmpeg from `imageio_ffmpeg`); 114 distinct frames in 3 s, upright, no vflip.
