---
name: MP scenario and UI census traps (w4863)
description: Traps hit while proving a presentation-only multiplayer feature (other players' placement ghosts) with a two-player ffnightly scenario, the ui_layout census and a long merge-gate test list
type: feedback
---

Learned on w4863 (FinalFactory PR #4016, other players' placement ghosts, lothdesktop, 2026-11-20).

**Two-player ffnightly scenarios**
- `ffauto:desync.stats` answers on the host only; read the matched/total counts there, not on the client.
- `blueprint.drop` puts the held item away but the hotbar will not re-hold it afterwards in the same
  scenario; to "put the item away" like a player, use a right-click (`pointer.click|1`).
- A client leave/rejoin is a `restart` step, and its `gapS` must be at least 12: the runner's liveness
  oracle refuses a shorter gap (the scenario failed with gapS 1).

**Running a long test list through the bridge**
- `unity-bridge.py call run_tests` with the merge gate's ~1050 class names fails with "Argument list too
  long". Import the bridge module from a small Python wrapper in `$TMPDIR` and pass the list there.
- If that call reports "bridge closed the connection", the job may still have started: read
  `mcpforunity://editor/state` for the running job id and poll `get_test_job` before starting another.

**ui_layout census for a UI PR**
- A census counts as "docked" only while the dock is up, i.e. a building is selected: place one and
  `ffauto:ui.selecttile|x|y` it. Selecting moves the camera onto the building, so a world-anchored label
  (the ghost's name) may leave the screen; say so in `Not verified:`.
- A DeckTour/station-tour `setup` ffauto step that needs `PlayersManager.Me` fails if it runs too early:
  put `{"waitFor": "name:Hotbars"}` first.
- `ui_layout.py check --touched` compares panels (Images) only. For a new TEXT element, take its `Style:`
  line from the census entries against its twin (here `PlayerNameTagController/NameTag0`): colour delta E,
  alpha, font size, drawn width, canvas order.
- `pr_evidence.py` must be the newest ff-agents version: an older cached plugin refused lines the current
  one accepts (`claude plugin marketplace update` then `claude plugin update ff-agents@final-factory-agents`).
