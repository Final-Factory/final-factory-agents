---
name: presentation-view-culling-needs-per-entity-reach
description: Skipping presentation work (spinners, interpolation) for entities out of view needs each entity's own measured reach plus its shadow, never a fixed margin; LifeSave census numbers and the bound that holds at every angle.
---

w1648 (2026-10-21) stopped spinners well out of view (#2144, `PresentationRotatorSystem`) and stopped smoothing moving
things well out of view (#2157, `WorldEntityInterpolationRenderSystem.OverwriteJob`), both against one
`PresentationView.Current` frustum (`Assets/Scripts/FFComponents/Presentation/PresentationView.cs`, a SharedStatic
written by `PlayerDataController.SetPresentationView`, invalid with the map open or no camera).

**A fixed margin is wrong.** The prototype used 80 u around the pivot. Reach measured on LifeSave (exact mesh spheres
through `RenderBounds` and `LocalToWorld`): Terra World 430 u, Antimatter Nexus 288 u, Luminae Obelisk 209 u, Celestara
Oracle 189 u, Neutron Star 138 u. Those would have frozen while their arms were on screen.

**The bound must hold at every angle.** A reach taken from the pose at tag time fell short for nested spinners. Use, per
child: `length(childOffset) + MaxScale(childMatrix) * childReach`, recursively, measured lazily the first frame the
hierarchy is in place (Reach 0 = unmeasured = always do the work). Follow the same children the work touches: for
interpolation, the brush rule (`MaxBrushDepth`, skip children with their own `WorldEntityPresentationInterpolation`).
Parts at zero scale (Defense Platform) show no reach; that is right, not a bug.

**Shadows show from off screen.** Nearly every moving unit casts a shadow and flies at y 0..40. The sun on the main scene
is 25 degrees up (`Skybox.prefab` Directional Light), so a shadow lands up to ~2.2x height away. Test the sphere and the
strip from the entity along `RenderSettings.sun` down to the lowest grid level (y -10, `GridHelper` MinGridTileHeight);
treat a sun lower than ~6 degrees as reaching everywhere.

**Margins:** add ~30 u for the camera moving on after the frame whose view was held. Judge both where the entity would be
drawn (the smoothed matrix) and where it stands (the stored matrix), and keep advancing the skipped entity's own
smoothing state so it is drawn smoothed the first frame it can show.

**The minimap reads presentation poses:** unit squares are brushed children read by `FlatMapMarkerRenderSystem`; at
42 u a pixel (ortho 5,392 on a 256 px texture) and at most 21.9 u a heartbeat step, an off-screen unit's square moves at
most ~0.5 px a step. Re-check that if the minimap texture or zoom grows.

Measured savings, Deck-like 4C/8T, 7 workers, 1x, prototypes: spinners -4%, interpolation -7%, both -11% CPU a second.
Off switches for A/B: `-ffSpinOffscreen`, `-ffInterpolateOffscreen`.
