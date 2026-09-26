# A transparent shader graph that writes no depth flickers where instances overlap

**Learned:** 2026-09-26, fixing the ice chunks that "z-fight" on cargo barges (Ben: it had bothered him for
years). Fix: develop `b334e573d`.

`Assets/Art/Shaders/IceShader.shadergraph` is in the transparent queue only so its Scene Color node can refract
the opaque texture. Its alpha is a constant 1, so it looks opaque. But ZWrite Control was **Auto**, which means
no depth write for a transparent surface. Every chunk then resolved by the per-object back-to-front distance
sort, not by depth. A barge stacks its cargo models so they interpenetrate (`LogisticsHelper.GetCargoOffset`:
~5.7-unit models every 3.5 units, layers 2.5 apart). A non-convex chunk also overlaps itself. Which chunk wins
each overlap flips as the camera or the barge moves, and that reads as z-fighting.

**Fix:** set ZWrite Control to **ForceEnabled** (`"m_ZWriteControl": 1` in the graph JSON). With alpha 1 there
is no blending to lose, the overlaps become depth-correct and stable, and the refraction is unchanged.

**How to spot the class:** a solid-looking mesh on a transparent-queue material (`renderQueue >= 2500`) that can
overlap itself or copies of itself. Scan the item and connector prefabs' renderers for that. Leave real
see-through surfaces (glass domes, beams, glows) alone: their blending needs depth write off.

**Repro rig:** instantiate the item's `Resources/ConnectorEntities/<Item>.prefab` GameObject in the barge
layout, move and turn the root a little every frame from an `EditorApplication.update` delegate, and grab frames
with `CometVfxGallery.StartFrames`. Compare the same frame zoomed in, before and after.
