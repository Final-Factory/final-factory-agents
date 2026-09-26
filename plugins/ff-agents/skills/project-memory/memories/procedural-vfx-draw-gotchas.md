# Procedural VFX draw gotchas (RenderPrimitives, Metal, stepped editor)

**Learned:** 2026-09-26, building the flying-station hover field (`Assets/Art/Shaders/Vfx/VfxHoverField.shader`,
`FFSystems.Presentation.HoverFieldVfxPresentationSystem`, develop `774452d40` + `52e500367`). They apply to any
presentation system that draws a procedural shader with `Graphics.RenderPrimitives` from a StructuredBuffer (the
beam, comet and hover-field VFX all do).

1. **`tanh` returns NaN on Metal for a large argument.** It expands to an `exp` that overflows. A tanh-based erf
   approximation has to clamp its input (`clamp(x, -3, 3)`). Without the clamp, every pixel beyond some distance
   went NaN and the effect became a hard-edged slab.
2. **`Material.SetFloat`/`SetBuffer` every frame on a material loaded from `Resources` writes into the `.mat`
   asset in the editor.** That causes git churn, and play-mode tweaks leak into the asset. Pass per-frame values
   through a `MaterialPropertyBlock` on `RenderParams.matProps`, and keep per-frame uniforms (a clock, buffer
   sizes) out of the shader's `Properties` block so they are never serialized. The same applies to tuning with
   `execute_code`: those `SetFloat` calls stick to the asset. Reset it before committing with
   `EditorUtility.CopySerialized(new Material(shader), asset)` and check the `.mat` diff.
3. **An `IJobEntity.Run()` in a presentation `SystemBase` that reads `LocalToWorld` through a `ComponentLookup`**
   throws a job-safety `InvalidOperationException` against `WorldEntityInterpolationRenderSystem:OverwriteJob`,
   and the system silently draws nothing. Create the lookups, call `CompleteDependency()`, then `Run`.
4. **`ProfilerRecorder` on a system marker records 0 samples in an occluded, `Step()`-pumped editor.** The marker
   is named `Default World <Namespace.SystemName>` in category Scripts. Time the system with a `Stopwatch` around
   `system.Update()` instead (`HoverFieldVfxGallery.SystemCost`).
5. **Culling bounds for quads laid out in a rotated local frame must reach the farthest rotated corner.** Use
   `length(max(abs(min), abs(max)))` + margin, not `cmax(abs(bounds))`. Otherwise the draw is culled when only a
   corner of a rotated station is on screen.
6. **To measure GPU cost, separate fixed cost from fill.** Push the quads off screen through the material (e.g. a
   huge vertical offset) and rerun the interleaved A/B. The hover field was about 0.25 ms fixed; the rest was
   fill, which grows with the screen area covered, not with the loop count per pixel.

**Getting a real multi-structure mobile station into a test game.** Hand-built blueprints rarely connect into one
station grid, because Standard structures need connector or strut bridges. Player blueprints do connect:
`~/Library/Application Support/Never Games/finalfactory/blueprints/*.bp` (JSON) →
`JsonUtility.FromJson` into `FFCore.Blueprints.Blueprint` → `Blueprints.BlueprintTool.GetFullBlueprintString` →
`ffauto:blueprint.place|<string>|x|z`. Then lift the station with `HoverFieldVfxGallery.Lift`, which sends an
`AddMoveStop` to its own position. On M3, "hub drones_ranzhans" (41 structures) and
"ursonator iii - ship_ranzhans" (598 structures, with rocket adapters) are good subjects.
