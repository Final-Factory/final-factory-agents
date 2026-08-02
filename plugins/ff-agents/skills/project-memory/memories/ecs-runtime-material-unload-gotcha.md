---
name: ecs-runtime-material-unload-gotcha
description: "Runtime new Material() in an ECS RenderMeshArray gets reaped by UnloadUnusedAssets unless HideFlags.HideAndDontSave is set, causing null-MaterialID BatchRendererGroup errors"
metadata: 
  node_type: memory
  type: project
  originSessionId: 3535008c-db26-4c83-beea-0296b7ded9dd
---

A `new Material(...)` created at runtime and referenced ONLY through an ECS `RenderMeshArray` shared component is NOT seen as "in use" by `Resources.UnloadUnusedAssets()` (Unity fires this automatically on scene loads / device resets). It gets destroyed while entities still hold its `BatchMaterialID`, producing: "A BatchDrawCommand was submitted with an invalid ... Material ID ... (`<null>`) ... SHADOWCASTER". Symptom tell: the shared/built-in mesh (e.g. Plane, fileID 10209) survives while the runtime material nulls out.

**Why:** ECS managed-shared-component references don't participate in Unity's asset-unload reachability the way native references do.

**How to apply:** On any runtime-created material fed into a `RenderMeshArray`, set `material.hideFlags = HideFlags.HideAndDontSave;`. Fixed at `StartController.InitializeActiveItemDisplays` (world item icons, `AsteroWorldIcon.prefab` — a built-in Plane) in commit `8f1c220a2`. Other runtime `new Material` sites to watch: `FogOfWarPlane.cs`, `GameObjectEntityConverter` (bakes MeshRenderer.sharedMaterials — risky when materials come from a mod AssetBundle that `ModInitializer.LoadModdedEntities` later `Unload()`s). Note the hideFlags approach leaks the material until app quit, so if a site re-runs per world-load, also track and `Destroy` the old materials.

**Single-point fix (implemented).** `StartController.PreventRenderAssetUnloading()` runs once after all entity prefabs load and walks every unique `RenderMeshArray` (`EntityManager.GetAllUniqueSharedComponentsManaged<RenderMeshArray>`), setting `hideFlags |= HideFlags.DontUnloadUnusedAsset` (NOT DontSave — baked assets must still save) on every material and mesh. This covers icons, warning/status indicators, AND buildable structure meshes in one place, so it's the real fix for the whole class — not per-prefab shadow toggling. Root cause was NOT shadows; shadows only determined which pass surfaced the null (off-screen billboards emit only SHADOWCASTER draws). Known gap: RenderMeshArrays created AFTER startup (runtime placement-preview/holographic models via `GameObjectEntityConverter`) aren't covered by the one-shot; protect at creation there if it ever surfaces.

**Related: shadow-caster spam from flat billboards.** The same null-`MaterialID`/`MeshID "Plane"` BRG error also fires on the SHADOWCASTER pass for the whole family of flat effect/indicator billboards under `Assets/Prefabs/EffectsEntities/`, `Assets/Prefabs/AbilityIndicators/`, plus `DeadPlayerMapDisplay`/`selectionRectangle` — they were ALL authored with `m_CastShadows: 1`/`m_ReceiveShadows: 1` despite being 2D UI billboards. Off-screen they emit ONLY shadow-pass draws, so you see SHADOWCASTER errors with no matching opaque-pass error. Fixed by setting both flags to 0 on all ~28 prefabs (Plane mesh = built-in fileID 10209). Any NEW flat indicator/billboard prefab should default to cast+receive shadows OFF. Prefab shadow mode is baked into the entity `RenderFilterSettings`, so changes need a subscene re-bake to take effect.
