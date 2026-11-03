---
name: a-check-proves-the-outcome-in-every-state
description: "A check, a fix's proof or a merge review's verdict proves the outcome a player sees, in every state the change touches, on the path the change claims: a toggle both on and off in a built player, combat by an enemy's health dropping (never a target acquired), a HUD layout with chat lines, the map and windows up at 1920x1080, 1280x800 and 1280x720. A red check made green by changing the check is the suspect, not the fix. A merge that got no review job is a miss, said in the night's report (w2976: four regressions of one playtest passed the nightly and its merge review)."
date: 2026-11-03
---

# A check proves the outcome, in every state, on the claimed path

**Rule.** Before you call a change verified (a fix's PR, a nightly check, a merge review's Duty A verdict), say which
outcome a player would see if it were broken and check that, not a step before it:

- **Every state the change touches.** A toggle, a filter or a mode is checked on and off, and opened and closed, in a
  built player, the path the PR claims first. Checking the path you expect to be the risky one is not checking the
  claim.
- **The outcome, not the intent.** Combat is checked by an enemy's health dropping or the enemy destroyed. A target
  acquired, an engage state or a weapon's cooldown running is a step before the outcome: it passes while nothing fires.
- **The screen a player has.** A HUD layout is judged with what is up at once in play: chat lines (they draw for about
  10 s after a line arrives, so a census taken with no chat line shows no chat), the map, a selected station and its
  windows, at 1920x1080, 1280x800 and 1280x720. A census of one element at a time passes a clash between two.
- **A relaxed check needs outcome proof.** A PR that makes a red check pass by changing the check (an invariant skipped
  for a case, an assert loosened, a scenario moved) is the suspect: the outcome is measured with the gameplay PR in and
  out before the relaxed check merges.
- **Coverage is counted.** A merge in the night's range with no review job is a miss, named in the report, never
  silently uncovered.

**Why.** In Loth's playtest of 2026-11-03, four regressions had passed both the nightly e2e and the nightly merge
review (game repo, w2976's investigation report):

1. *The minimap showed Signal whenever it was on.* #3068 (w2919) was verified in the editor only. The map-window
   review (w2951) checked the reverse path (Signal off when the minimap was off), not the one the PR changed. No
   minimap scenario existed. **A check of the wrong path.**
2. *The world map's icon zoom changed the minimap's icons.* Both draw the shared MapMarker. w2951 never toggled the
   zoom with the minimap up. **A check never run.**
3. *Defense-platform drones engaged and never shot.* #2923 (w2674) locked targets in the fog, and the nightly went red
   on 11-01. #2971 (w2773) then exempted the case in `FleetEngageMonitor` and moved the Gatling scenario, and the
   nightly went green. w2950 (#3091) proved the later fix #3080 with asserts on the Targeter only. #2923 got no Duty A
   job. **A check weakened to fit, then an outcome never asserted.**
4. *Station Info sat under the chat.* #2995 (w2580) moved Station Info into chat's bottom-left column, and #3072 kept it
   there. Both HUD-layout verifiers (w2879, w2952) took censuses with no chat line drawn. **A scenario on the wrong
   path.** w2976's first census with chat (`UI-w2976-hud-with-chat`, a development player of 877c90602) failed
   at once: at 1280x720 the chat lines cover the Objectives card.

**How to apply.**

- Write the outcome as the assert: `health.current` with `atMost`, an enemies `count` of 0, an element on screen in the
  census (`mustShow`), a pixel or icon size measured in both toggle states.
- In the game repo, `scripts/nightly/combat-damage.json` maps every attacker kind to a scenario that asserts damage.
  `combat_damage.py check` (in `ffnightly.py ledger-check --ci`) fails a scenario with no damage assert, and a kind with
  no scenario must carry a `gap` with its reason. `deck_lane.py`'s `strict` makes a chat overlap a finding whatever the
  baseline holds, and `mustShow` makes a still with no chat line drawn a finding.
- The merge review's charter (`scripts/nightly/merge-review.md`) carries the same lines: a relaxed check is HIGH, and a
  UI, layout or combat suspect's verdict rests on these outcomes.
- Checklists: [merge](../checklists/merge.md) ("A fix is proven by the outcome, in every state") and
  [UI](../checklists/ui.md) item 11 (chat lines, the map, three sizes).
