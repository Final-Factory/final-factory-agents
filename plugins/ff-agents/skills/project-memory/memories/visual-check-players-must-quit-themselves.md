---
name: visual-check-players-must-quit-themselves
description: "A built player started for a look or a clip (player_slots.py launch, -ffSoloNewGame) cannot be closed by an agent once it is paused in its Esc menu or back at the title screen: the agent channel refuses every command there (state_not_playable), net.hostquit leaves the process at the title, and the harness blocks killing game processes. It keeps the sandbox's player slot, and the next launch is refused. Always pass -ffSoloQuitAfterSeconds <n>; never press Escape with nothing in hand"
metadata:
  type: project
---

**What happened (2026-10-07, w503, m5/slot3).** Three players launched with `player_slots.py launch --detach
<build> -- -ffAgentControl true -ffAgentControlDev true -ffSoloNewGame <seed> ...` for panel stills and clips
ended up holding both of the sandbox's player slots (3-0, 3-1) with no way to close them:

- one was **paused in its Esc menu**: an `ffauto:pointer.holdkey|Escape` meant to drop a blueprint from the
  hand opened the menu instead, because nothing was in hand. In single player the menu pauses the game, and
  `POST /v1/command` then answers `409 state_not_playable` ("the game is 'paused'") to everything, including
  `ffauto:ui.menu|close`;
- one was at the **title screen** after `ffauto:net.hostquit` ("host ended the session ... shutdown"), which ends
  the session but not the process; the agent channel refuses commands on the title screen too;
- `kill` of a game process is refused by the FF Factory harness hook ("Killing Unity ... processes by hand is
  blocked"), so only a person or the daemon could free the slots. `ffnightly.py run` was refused meanwhile
  (`SlotRequired`: no free slot of the sandbox's pair).

**How to apply.**

- Start every look/clip player with **`-ffSoloQuitAfterSeconds <n>`** (`NightlySoloBootstrap.QuitAfterArg`): it
  calls `Application.Quit` after n seconds of real time. Pick n to cover the work (e.g. 1800).
- Press Escape only to drop something actually in hand (a blueprint placed with `blueprint.place` stays in hand:
  the cursor hint "Rotate [R], flip [Shift+H] [Shift+V]" shows it). With nothing in hand, Escape opens the menu.
- A player of the same build shares its slot (`player_slots.py`: same sha and fingerprint), so a second look at
  that build still launches; a different build needs a free slot.
- Before ending a turn, check your players with `ps` against your lease files
  (`player_slots.py status`) and say which are still running.

See [[feedback-built-players-run-from-the-slot-pool]].
