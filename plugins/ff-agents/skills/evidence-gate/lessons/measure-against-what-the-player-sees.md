---
name: measure-against-what-the-player-sees
description: "A placement or alignment metric is measured against what the player sees (the drawn hull's surface, the visible edge, the drawn position), never against the system's own notion of the answer (the simulated hit point, the value the code computed). A metric that compares the code with itself reads 0 while the bug is on screen."
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
