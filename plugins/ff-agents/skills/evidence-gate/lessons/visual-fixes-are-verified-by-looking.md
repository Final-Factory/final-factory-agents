---
name: visual-fixes-are-verified-by-looking
description: "A visual or feel fix is done only when someone looked at it: a built player, a clip that contains the event, compared with the intended look in the person's own words. Measurements and watch_video support the look; they do not replace it."
date: 2026-10-11
---

# A visual fix is verified by looking

**Rule.** A change a player sees is verified in a built player, with before and after clips that
contain the event, checked frame by frame against the intended look as the person described it.
`watch_video` and its blind model review are a second opinion. A measurement, a pull request
title or a tool verdict is not a look.

**Why.** Three fixes merged on 2026-10-01 and 02 on evidence for a different claim.

- **Two players on one mobile station (#884).** Verified by position numbers: the other rider's
  ship was 0.0 units from its seat. In the 0.50.0.64 build Ben found the rider still drawn with
  engine exhaust. The numbers measured where the ship was, not how it looked.
- **Miner bot death explosions (#886).** The proof was frame sequences from an editor rig; the
  pull request says "No real station was deconstructed". It merged 39 minutes after it opened. In
  the same build Ben found the explosion still huge.
- **Quick craft asking for an item a bot is carrying (#913).** Merged 37 minutes after it opened
  with "The `watch_video` review is pending". Its clips were editor frames at about 12 fps, and
  by the orchestrator's account they did not contain the moment the report was about.

The orchestrator had reported the first two to Ben as fixed. Ben: "did you even visually verify
this", "VISUALLY VERIFY STUFF WITH VIDEO". Its record of that week also says the blind model
review passed clips that did not contain the event, and approved a mistake because the brief
described the mistake as the intended look.

**How to apply.** [The visual checklist](../checklists/visual.md), in short:

- Quote the person's description of what is wrong or what they want. Don't review against your
  own description alone.
- A built player from the slot pool, and the real event reached the way a player reaches it.
- Name the frames where the event is. Step through them yourself, at a zoom where the detail
  shows.
- Report what you looked at. "Fixed" is for what was seen; otherwise say "changed, not yet seen
  in a built game".
- An orchestrator does not report a visual fix as done from a title, a table or a verdict. It
  says what evidence the worker named.

## Hunt for what should not be there (w895, w1015)

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
   [visual.md](../checklists/visual.md) item 5b (Artifact hunt).
