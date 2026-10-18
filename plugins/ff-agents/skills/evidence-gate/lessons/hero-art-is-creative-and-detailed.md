---
name: hero-art-is-creative-and-detailed
description: "New hero art (a model, a hero or end-game weapon's VFX) is not shown to Ben as one literal, generic or under-detailed take (w1470, w1466, 2026-10-18): the first look is 2 or 3 clearly different concepts; a concept that is a literal real-world object (a bow, a disc) is reinterpreted for space and sci-fi; the model's detail is compared with the game's best models of the same class in one still and the comparison is named; a new weapon's projectile and impact are compared with the Railgun, Plasma Bolt and the others and read clearly different, any reuse called out; and the gate's verdict says what makes the piece distinctive, not only that it passes. Extends the art-language rule (colour, accent, no overlay) with 'is it creative and detailed enough for its role'."
date: 2026-10-18
---

# Hero art is creative and detailed, not literal or generic (w1470, w1466)

**Rule.** Before a new **model** or a **hero VFX** (an end-game or siege weapon's projectile and impact, a boss,
a signature ship or building) goes to Ben:

1. **2 or 3 clearly different concepts come first, not one.** Different silhouettes or different ideas, not three
   colourings of one. Ben picks or redirects; he is not handed the one take you happened to build. Say in a line
   what each concept is.
2. **A literal real-world object is reinterpreted for space and sci-fi.** If the idea is a bow, a disc, a lance, a
   crossbow, a cannon, a shield or a spear, build what that thing would be as a space weapon (an energy-loaded
   frame, a field, a tether, a rail of light), keeping the idea and not the object's shape. The test: would a
   player who did not read the name see "a bow" or "a disc" at once? Then it is too literal.
3. **The model's detail is compared with the game's best models of the same class, side by side in one still.**
   Same camera, lighting and bloom, the new ship or building next to the best existing ones of its class (the
   most detailed battleships or siege ships; the Railgun and the other detailed powered buildings). Name them in
   the evidence. Judge panel lines, greebles, mass, silhouette breaks and the emissive accents, and say where the
   new model is at least as rich. A model that reads as a flat primitive set beside them is not shown.
4. **A new weapon's projectile and impact are compared with the existing weapons' and read clearly different.**
   Put the projectile and the impact in one still or clip next to the Railgun, the Plasma Bolt and the other
   weapons' (same zoom), and say what differs in shape, colour, motion and how long it lasts. **Any reuse of
   another weapon's effect (its orb, flash, shockwave, spark burst) is named as reuse** and justified or replaced;
   reuse you leave unnamed is a miss.
5. **The gate's verdict says what makes the piece distinctive**, in a sentence a player could repeat ("the Lance is
   a tether of purple light that pulls the target in; the impact folds the hull inward"), not only "passes the
   art-language check". If you cannot write that sentence, the piece is generic: go back to step 1.

This stacks with the art-language rule (two solid colours plus one bloomy HDR accent, the object's own light and
never a halo,
[section](visual-fixes-are-verified-by-looking.md#new-art-matches-final-factorys-art-language-w1066-w1241-w1332)):
that rule asks "does it belong to the game"; this one asks "is it good enough for its role".

**Why.** Ben corrected the same kind of miss twice on 2026-10-18, each time on art the worker had passed and the
orchestrator had let through.

- **w1470, Singularity Lance (PR #1921).** A flat black disc over a purple disc, with the Plasma Bolt orb reused as
  the projectile. Ben: "I don't like that it's just like a black disc sitting on top of the purple accretion disc
  ... this is the end game weapon that needs to look really cool ... be creative with this."
- **w1466, Urso Ballista siege ship (PR #1929).** A ship built as a bow and arrow, with an impact that looked like
  the others. Ben: "i dont like that its so explicitly like a bow and arrow. we are in space, so you can use this
  concept but be more creative and futuristic, and the model itself is not detailed enough. we need high quality
  models" and "can we get more creative on the impact effect? it looks samey with all the other effects,
  especially the railgun effeect".

Both passed because the checks asked "is the requested thing there, in the game's colours?" and never "is it the
best idea for it, as detailed as our best, and different from what we already have?". One take was built and
polished; nothing forced a second concept, a reinterpretation, a detail comparison, or a comparison of the impact
with the other weapons'. That is two corrections of one kind in a day, so it is now a checklist item
([visual checklist 5e](../checklists/visual.md)).

**How to apply.** At design time, before building: write the 2 or 3 concepts (one line each, with the literal
object each starts from and what it becomes in space), and for a weapon list the existing weapons' effects you
must differ from. Show Ben the concepts (a still of each, or a quick block-out) and build the one he picks, or the
strongest if he said to decide. Before the preview: the one detail still against the named reference models, the
projectile and impact next to the Railgun and Plasma Bolt, the reuse list, and the distinct-because sentence. The
PR's `## Evidence` carries a `Hero art:` line naming the concepts offered, the detail reference models, the weapons
compared and the distinct-because sentence; a hero asset without them is not shown and not merged.

**Not automated yet.** `pr_evidence.py` cannot tell a hero asset from other new art (it sees changed shader,
material and VFX files, not a new model's role), so this rests on the checklist and on the orchestrator reading the
report. If a third correction of this kind comes, add the `Hero art:` field check to `pr_evidence.py` with the
w1470 and w1466 PR bodies as fixtures.
