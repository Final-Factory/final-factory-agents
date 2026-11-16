---
description: On a Mac a built player cannot be killed by hand (the harness refuses kill); quit it with osascript Cmd-Q, which writes _autosave_sp_before_quit_N_<save> files to delete. A tooltip text change under Assets/Scripts/UI/ still needs the whole Kind: ui ritual; compare Style against the before build's twin card.
---

# Quitting a Mac player, and the UI evidence for a tooltip text change (w4360, 2026-11-16)

## Quit a built Mac player without kill

The harness refuses `kill` of a game player. Bring it to the front by its unix id and send Cmd-Q:

```sh
osascript -e 'tell application "System Events" to set frontmost of (first process whose unix id is '"$PID"') to true' \
          -e 'tell application "System Events" to keystroke "q" using command down'
```

The game then saves `_autosave_sp_before_quit_N_<save>.zip` and `.jpg` into
`~/Library/Application Support/Never Games/finalfactory/UserData/saves/`. Delete yours (only yours: by the save
name you loaded). Better: launch with `-ffSoloQuitAfterSeconds <n>` so it ends by itself.

## A tooltip text-only change still gets the full Kind: ui ritual

w4360 changed only a case in `TooltipPanel.cs` (a new station warning sentence). Any file under `/UI/` makes
`pr_evidence.py` demand `Kind: ui` and every UI line (Style, Pinned, Shape, Looked, Real Deck, Determinism audit...).
What cost re-runs:
- **Style**: compare the new card against the before build's twin of the same card (an existing station warning
  card), not against an item tooltip: the red warning header measured delta E 63.6 against the blue item header and
  failed; against the before warning card it was 0.0.
- **Pinned**: take the 1920x1080 station census with the Station Info window up, or its pins count as "not shown".
- Keep every census folder until `pr_evidence.py` passes; the lines are recomputed from them.
- Precedent PR: FinalFactory #3615.
