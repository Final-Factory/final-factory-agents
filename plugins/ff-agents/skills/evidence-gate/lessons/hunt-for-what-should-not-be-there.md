---
name: hunt-for-what-should-not-be-there
description: "Checking stills and clips against the brief finds only what was asked for. Before saying a visual 'matches', list what is visible that nobody asked for: ghosts, leftovers, dark silhouettes, stale UI, overlaps, z-order errors, flicker, clipped text."
date: 2026-10-11
---

# Hunt for what should not be there

**Rule.** A visual check has two questions, asked separately: (1) is each thing the brief asked for
there, and (2) what is on screen that the brief did not ask for? Answer (2) for every still and every
frame of every sheet, as a written list: duplicate or leftover objects, ghost copies, dark or unlit
silhouettes, stale UI, things overlapping or drawn on the wrong layer, flicker, clipped text. Each
item is explained (and the person would call it intended) or fixed before the word "matches".

**Why.** Ben corrected the same miss twice.

- **w895, PR #1406 v2 (2026-10-10).** The worker verified a hover card by a measurement (census
  depth) instead of looking at the still. The card still read on top of the Defense Platform panel.
  Ben: "the hover panel is clearly showing over the defense platform and then also intersecting with,
  like, those sliders and stuff, which is bad, but it should just be behind the panels altogether."
- **w1015, victory cinematic, PR #1487 (2026-10-11).** The worker checked sixteen labelled frames and
  said they "match" Ben's six steps. The clip shows a dark ghost copy of the vessel left behind during
  the pan. Ben: "why is there a black ghost vessel that stays behind, it looks weird".

In both, the evidence was read against the request ("is X there?"), so anything extra was invisible
to the check: nobody was looking for it.

**How to apply.**

1. After the "matches the brief" pass, do a second pass with the brief closed. Per frame write one
   line: what is visible that was not asked for, or "looked for ghosts, leftovers, silhouettes,
   stale UI, overlaps, z-order, flicker, clipped text: none".
2. Zoom on the moving thing's start position, the area behind a camera pan, and every edge where two
   panels or objects meet. Ghosts live where the object was a moment ago.
3. `watch_video --mode vfx` has an "Out of place" section answered without the brief. It is a second
   opinion: read it, then look yourself; its silence clears nothing.
4. Put the list in the report under "Looked for, not asked for". The checklist line is
   [visual.md](../checklists/visual.md) item 5b.
