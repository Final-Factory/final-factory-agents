---
name: measure-against-what-the-player-sees
description: "A placement or alignment metric is measured against what the player sees (the drawn hull's surface, the visible edge, the drawn position), never against the system's own notion of the answer (the simulated hit point, the value the code computed). A metric that compares the code with itself reads 0 while the bug is on screen. A check, a fix's proof or a merge review's verdict proves the outcome a player sees, in every state the change touches, on the path it claims: a toggle on and off in a built player, combat by an enemy's health dropping (never a target acquired), a HUD layout with chat lines and the map up at 1920x1080, 1280x800 and 1280x720; a red check made green by changing the check is the suspect, and a merge with no review job is a named miss (w2976)."
date: 2026-10-07
---

# Measure against what the player sees

**Rule.** When you verify where something is drawn (an impact, a beam end, a marker, a label, a
ghost), measure it against the thing the player looks at: the target's drawn surface, its visible
outline, its drawn position this frame. Do not measure it against the place the code meant to put
it (the simulated hit point, the value the system computed, the input to the fix). Write down what
the player should see first ("the flash on the hull's side facing the shooter"), then pick a
metric that would read badly if that were not true. If the metric's reference comes from the same
code path as the thing you measure, it checks the code against itself.

**Why.** w176 (PR #909, merged as `6a8d41341`, 2026-10) set out to make impact effects land on
what is drawn. It carried the simulated hit point onto the target as drawn and measured each effect
against that same carried point (`scripts/feel/analyze_impact_vfx.py`, `onTarget`): 0.0 u on 51
hits on moving targets. Beams were scored against the target's drawn centre. Both references were
the system's own answer. But a KNN hit fires when a bolt comes within 10-15 u of the target's
**centre** and the effect is then pushed 5 u on, and a beam ends at the centre: on a Razor (39 x 30
u) the effect sat inside the hull, at or past its middle. Ben saw it in Builds 82/83 as host
(w587): "impact effects are still landing behind targets instead of more accurately at the point
of impact". The metric could not see it, because nothing in it knew where the hull's surface was.
w587 then caught two more wrong references while fixing it: a bounding box put the surface up to
13 u in front of a Razor's real mesh, and a per-kind outline taken once missed a Krillo's claws in
other poses. Both were found only by checking each effect against the target's exact mesh on the
frame it was drawn (the probe's `S` lines, `ImpactOutlineCheck`).

**How to apply.**

- Name the visible reference before you measure: for a hit, the drawn hull's outline (its mesh, as
  the camera sees it); for a beam, the drawn target's near surface; for a marker, the drawn object.
- Compute that reference independently of the code under test: from the drawn meshes or poses this
  frame, not from a value the fix produces or consumes. If the fix approximates the shape (a box, a
  grid), the check uses the exact shape.
- Sweep it: every kind of target the code draws on, moving and still, every pose a part can be in,
  shots that cross the target and shots that graze it. A table per kind, not one average.
- Prove the metric can fail: run it on the "before" arm (a launch flag that restores the old
  behaviour) and show it reading badly there.

**Moving things, and the clips themselves (w1086, 2026-10-12).** Measure a change to how something moves on things that
MOVE: a backed-up belt parks its items, parked entities are drawn at their simulation position (the interpolation
render skips them, w950), so a before and after of a full belt are the same picture. Film the first seconds after the
line is built, or give it a sink that takes the flow (an unpowered Cargo Hold refuses items). Before taking a number
from a clip, look at its first still (a recorder grabs a screen region, so another window on top is recorded:
w1086's first clips were WinDirStat, `raise_window` passed HWND_TOPMOST as a 32-bit int) and read its `ffprobe` size
(the old nightly player re-applies a stored window size on some launches: 1280x800 before, 1920x1080 after).
w1086, belt items drawn on a quarter circle 2.07 u inside the L-shaped curve piece's middle: lothsahn, "Tell the w1086
worker to do it rendered and not guess"; the tubes' centre line, fitted from the frame, was the reference, with
`scripts/feel/run_w1086_belt_corners.py` and `analyze_w1086_corners.py` as the pattern. A stop that wipes the temp
folder loses clips: `publish_review` them as soon as they exist.

The checklist line: [visual changes](../checklists/visual.md), item 0c.

## A check proves the outcome, in every state, on the claimed path (w2976, 2026-11-03)

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
