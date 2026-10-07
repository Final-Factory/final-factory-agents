---
name: check-every-kind-of-object-shared-presentation-draws
description: "A change to shared presentation code (selection and hover boxes, highlights, outlines, icons, health bars, info panels) is verified on every kind of object that code draws, moving, rotating and spinning ones included, not only on the case the change was for. A component used to pick out one kind ('Placeable means a structure') is checked against every archetype that carries it."
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
