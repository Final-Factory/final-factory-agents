---
name: new-art-matches-the-art-language
description: "New models, materials and highlights follow Final Factory's art language: two solid main colours plus one bright, bloomy HDR accent, and a highlight is the object's own material glowing, never a world-space halo, ring or UI-like indicator. Compare side by side with an existing reference asset before any preview goes to Ben."
date: 2026-10-13
---

# New art matches Final Factory's art language

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

**How to apply.** [The visual checklist](../checklists/visual.md) item 5c. For a glow, change the
emissive colour or intensity on the object's own material (a property block or a material
instance), not a new child sprite or mesh that sits around it. Name the reference asset and
attach the side-by-side still in the PR's `## Evidence` (the `Intended look` line or the
`Shots:` line). If you think the brief really wants an indicator, quote where it says so.
