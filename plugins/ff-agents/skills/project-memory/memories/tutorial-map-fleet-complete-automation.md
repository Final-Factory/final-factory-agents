---
name: tutorial-map-fleet-complete-automation
description: "How the last three tutorial objectives complete from the harness: ui.open|map then ui.close|map (MapUsed ticks on CLOSE), ui.open|fleet, and the final Complete button is a LOCAL click on EVERY peer."
---

# Tutorial objectives 76–78 from the harness (live-proven 2026-09-11, build 2a0ce38bb)

- **76 "Open the map"**: `ffauto:ui.open|map` → `ffauto:wait|2` → `ffauto:ui.close|map`. The
  `map` panel entry (AutomationUiDriver, alias `worldmap`) drives
  `WorldMapControlAction.OpenMap/CloseMap` — the [M] key's path — and the objective's
  `MapUsed` counter ticks in **CloseMap** (`WorldMapControlAction.cs:86`), so open alone never
  completes it.
- **77 "Fleet panel"**: `ffauto:ui.open|fleet` → `ffauto:wait|2` → `ffauto:ui.close|fleet`.
- **78 "You have completed the tutorial"**: its verifier is `DontVerify`; the card's Complete
  button is the only skip allowed. The click is **local to each peer**
  (`ObjectivesController.cs:63` → `CompleteSingleObjective`; only verifier-driven objectives
  follow the host's tracker projection), so click it on the host AND on the client. Screenshot
  → button pixel → native pointer coords: host 1280x691 shot `(47,224)` → `pointer.moveto|94|934|screen`;
  client 1280x800 shot `(45,215)` → `pointer.moveto|90|1170|screen`; then `wait|1`,
  `pointer.click`, `wait|2`, `pointer.clear`. Verify with `ffauto:observe.state|objectives`
  (`data.current.shortDescription` becomes "Automate Bat production", `completed` = 74).

The whole run (resume from `claude_tutorial_012_at_map_objective`, both peers through 78,
typed comparator pass on 3,036 samples with 0 mismatches) is recorded in
`/private/tmp/ff-tutorial-2a0ce38bb/RUN-NOTES.md` on the M5; the completed world is saved as
`claude_tutorial_complete_2a0ce38bb`.
