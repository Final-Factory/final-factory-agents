---
name: check-every-kind-of-object-shared-presentation-draws
description: "A change to shared presentation code (selection and hover boxes, highlights, outlines, icons, health bars, info panels) is verified on every kind of object that code draws, moving, rotating and spinning ones included, not only on the case the change was for. A component used to pick out one kind ('Placeable means a structure') is checked against every archetype that carries it. A hide or visibility change hides every visual the thing carries, its children and the separate entities that follow it, proven by a built-game census of what is still drawn inside its bounds (w2210)."
date: 2026-10-07
---

# Check every kind of object shared presentation code draws

**Rule.** Before you change code that draws something for many kinds of object (the hover and
selection boxes, highlights, station outlines, Alt-view icons, health bars, hover panels, range
rings), list the kinds that reach it and verify each one, not only the one you are fixing. Include
the ones that move by themselves: spinning comet fragments, tumbling asteroids, turning ships,
enemies, things on a flying station. When the change behaves differently for one kind, the test
that tells the kinds apart (a component, a tag, a config flag) is a claim: check it against every
archetype that carries it before you build on it.

**Why.** w453 (#1093, commit afc42e60d, merged 2026-10-06, first shipped in 0.50.0.80) made the
selection box on a flying station's building follow the building as drawn, and turn with the
station. `SelectionMarkerLookSystem.DrawnQuad` turned the box with the target's drawn rotation
whenever the target had a `Placeable`, read as "a structure". Asteroids, comet fragments and
treasures carry `Placeable` too (`WorldObjectGeneratorJob.cs:415`), and a comet fragment's root
tumbles (`RotationParameters`, `AutoRotatorSystem`). From 0.50.0.80 every hovered comet fragment
had a box that spun and tipped with it. Ben found it playtesting Builds 82/83 (w586): "the hover
selection boxes rotate with the thing you are selecting, especially a problem for comet fragments
that you mine". #1093's evidence was thorough for its own case: probes on every frame of a built
player, before/after clips in single-player and two-peer play, a frame-by-frame look. All of it was
on one fixture, a Hydro Power Radiator on a flying station. Its "Not verified" list never asked what
else the box is drawn on. Its unit test checked that a landed structure keeps its box, and that a
target with no `Placeable` keeps its box. No test had a `Placeable` that is not a structure. The fix
(w586, #1176) turns the box only for a station structure (`StationGridReference` to a grid, no
`RotationParameters` on the target), with a test for a spinning comet fragment.

**How to apply.**

- Find every caller and every kind of target first: grep the writers (for the boxes,
  `MouseRaycastSystem`, `MultiSelectHoverMarkerSystem`, `MassDriverLinkHighlightSystem`) and list
  what can be hovered or selected: buildings landed and on a flying station, asteroids, comet
  fragments, treasures, ships, enemies and their camps. Name them in the plan.
- For a discriminator, count it in a running game, not from its name: for example, iterate
  `ItemConfig.ItemPrefabs` in play mode and print which prefabs carry the component, with and
  without the other components that matter. Every kind that carries it is in scope.
- Write a test per kind that differs: at least one that must keep the old behaviour (the comet
  fragment in `SelectionMarkerFollowsDrawnPoseTest`), and prove it RED against the change.
- In the built-player before/after, film the case you fixed and at least one other kind that goes
  through the same code, a moving or spinning one if there is any. If you leave a kind out, put it
  under "Not verified" by name.

The checklist line: [visual changes](../checklists/visual.md), item 0b. The sibling rule for shared
shaders and materials: [check who uses a shared asset](check-who-uses-a-shared-asset.md).

## A hide hides everything the thing carries, proven by a census (w2210)

**Rule.** A change that hides, culls or toggles the visibility of a thing in the world (a view toggle such as F7's Hide
Flying Stations or Hide Cargo Barges, the fog, a ship stowed or ridden, a ghost hidden over the UI) first lists every
visual that thing can carry: its children, and the separate entities and GameObjects that follow it without being its
children (VFX graphs, particles, shields, engine and thruster flames, lights and lamps, trails, beams, outlines,
selection boxes, labels, icons, health bars, items on its belts and in its hands). Then it proves the hide in a built
game by a census, not by the list: with the thing hidden, count the renderers, particle systems and VFX still drawn
inside its bounds. The answer is 0, or each one left is named with why it stays.

**Why.** Hide Flying Stations shipped by w1320 (#1766, re-landed as #1790 by w1365) and was then fixed one leftover at a
time, each PR listing by hand what it hid. Belt items stayed drawn on a hidden station (w1435, #1861). Then the hover
field and beams; Ben, w1909 (#2345, merged 2026-10-23): "also the visual effect on floating stations, the hovering wispy
effect, doesnt disappear when you hide mobile stations, they should also disappear, it looks weird to show that wispy
outline and theres no ship there". Then, on 2026-10-25 (w2209): "hiding mobile stations should hide any shielding they
have and the rocket engine effects. and anything else, you keep missing stuff". Every one of those leftovers is a
separate entity or GameObject that follows the station (a VFX graph, a shield, an engine effect, an item entity), so a
hide that walks the station's own children never reaches it, and a hand list misses whatever its author did not think
of. A count of what is still drawn there catches all of them at once.

**How to apply.**

1. Before writing the hide, find what follows the thing: grep the systems that place visuals by its entity (a parent
   or owner field, a `Follow`/`Attached`/`Owner` reference, a presentation system that reads its pose) as well as its
   children. Name every kind in the plan.
2. In a built player (the slot pool), hide it and run the census: every enabled renderer, particle system and VFX
   (entity `MaterialMeshInfo` enabled and `DisableRendering` absent, GameObject `Renderer.enabled`,
   `ParticleSystem.isPlaying` or emitting, `VisualEffect` alive with particles) whose bounds meet the hidden thing's
   bounds. Do it with every carried visual live: shields up, engines firing, a hover field, beams, items on belts. Save
   the census (json or log) and film the hide at 60 fps.
3. Put the `Hidden census:` line in the Evidence ([checklist 5l](../checklists/visual.md), merge.md):
   `Hidden census: <census log, clip>: with <the thing> hidden in a built player, 0 renderers, particle systems and VFX
   still drawn inside its bounds; it carries <every kind>`. `pr_evidence.py` fails a PR that changes a game script named
   for hiding, showing or culling (`…Visibility…`, `…Hide…`, `…Hidden…`, `…Cull…`; not UI, the lobby, probes or
   audits) without it, or with `n/a` and no reason (a revert, selection or input only, who owns the setting). On the
   game repo's 947 merged PRs of 2026-10-01..25 it fired on 15: 11 changed what a hide draws, 4 would write `n/a`
   (#1158 a release, #1780 a revert, #1836 selection only, #1940 who owns the setting).
4. The fresh critic is asked "is anything still drawn where the hidden thing was?" on the clip (`pr_evidence.py --note`,
   ui-critic step 7c).

What the tool cannot see: a hide written in a file whose name does not say so (a renderer switched off inside an
unrelated system). The rule holds there too; write the line anyway.
