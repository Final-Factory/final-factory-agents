---
name: visual-fixes-are-verified-by-looking
description: "A visual or feel fix is done only when someone looked at it (new art also matches the art language, checked against a reference asset): a built player, a clip that contains the event, compared with the intended look in the person's own words. Measurements and watch_video support the look; they do not replace it."
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

## New art matches Final Factory's art language (w1066, w1241)

**Rule.** Before a preview of new art (a model, a material, a glow, a highlight) goes to Ben:

1. **Two solid main colours and one bright, bloomy HDR accent.** That is how the existing
   powered buildings and ships are built. A new model or material gets the same three parts: no
   extra palette, no flat all-over tint, no missing accent.
2. **A highlight is the object's own material.** To mark something in the world (a powered
   building, a stronger enemy, a selected thing) drive its emissive/HDR accent so it blooms, or add
   rim light, the way the existing buildings and ships are lit. Do not add a world-space sprite,
   halo, ring, aura or any UI-like indicator drawn around it, unless the brief asks for an
   indicator.
3. **Side by side with a reference, in one still.** Put the new asset next to an existing one that
   is built the right way (the Railgun, other powered buildings, existing enemy ships), same camera,
   same lighting, bloom on. Look at it yourself: do the main colours, the accent and the glow read
   as the same family?
4. **The PR's evidence names the reference asset compared and shows that still.**

**Why.** Ben corrected the same kind of miss twice on 2026-10-13.

- **w1066, assembler makeover, PR #1683.** The new assemblers had no bright accent. Ben: "final
  factory art is characterized by basically two solid main colors, then an HRD color that is
  bright and bloomy. look at any other powered building, including the railgun which you made. you
  didnt add this to the assemblers here".
- **w1241, super enemies, PR #1678.** The super's look was a gold halo around the ship. Ben: "i
  dont like that the glow effect is more like a world space UI indicator, isntead of making the
  ship itself glow more naturally".

Both passed the worker's own check, because that check asked "is the requested look there?" and
never "does it look like the rest of the game?". Neither worker held the new asset up against an
existing one.

**How to apply.** [The visual checklist](../checklists/visual.md) item 5c (Art language). For a glow, change the
emissive colour or intensity on the object's own material (a property block or a material
instance), not a new child sprite or mesh that sits around it. Name the reference asset and
attach the side-by-side still in the PR's `## Evidence` (the `Intended look` line or the
`Shots:` line). If you think the brief really wants an indicator, quote where it says so.
