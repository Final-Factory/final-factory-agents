---
name: linkedentitygroup-dangling-entry-and-clone-aliasing
description: "Two LinkedEntityGroup rules learned from the tutorial re-place crash (Burst abort 'srcEntity's LinkedEntityGroup references an entity that is invalid'): never link a set that has a dead member and never destroy a linked child without unlinking; and Instantiate remaps only the source's OWN group, so a nested child left out of it is SHARED by the clone. Includes the integrity-scan probe and the unlink-now/destroy-later trap."
---

# LinkedEntityGroup: dangling entries and clone aliasing (2026-09-11/12, 069)

**Crash class.** A child appended to a parent's `LinkedEntityGroup` and later destroyed without
being unlinked kills the NEXT `Instantiate` of that parent: ECB playback throws
`ArgumentException: The srcEntity's LinkedEntityGroup references an entity that is invalid
(Entity at index N)` from `AssertCanInstantiateEntities`, which in a built player is a Burst abort
(`Trace/BPT trap: 5`, an `.ips` crash log on macOS). Seen on the Hand-Hold tutorial's objective 13
(re-place the Mining Station) in runs 3 and 4: the placement preview carried dead entries.

**Probe that finds the owner in seconds.** Iterate every entity with `LinkedEntityGroup`
(`EntityQueryOptions.IncludePrefab | IncludeDisabledEntities`) and report entries where
`!EntityManager.Exists(entry)`; print the owner's marker components and the group length. Run it
right after each step of the repro (select item → place → remove → re-select). In the editor via
the `unity` CLI: `eval_file --file <scan>.cs` ([[editor-via-unity-cli-when-the-bridge-is-down]]).

**Why the first fix (unlink on destroy, `3f2866af7`) was NOT enough — two more rules.**
1. **Clone aliasing.** `Instantiate` remaps entity references only against entities inside the
   source's own `LinkedEntityGroup`. `TerrainExtractorTerrainItemFinderSystem` appended only the
   route ARROW to the preview's group; the arrow's route/start/end lived in the arrow's nested group.
   When `BlueprintPlacerJob` cloned the preview (`BlueprintPlacementSystem.cs:792` — the ORIGINAL
   becomes the structure, the CLONE the next preview), the clone's arrow SHARED route/start/end with
   the structure's arrow. Removing the structure destroyed the shared children under the clone.
   Rule: **link every child you may clone** into the top-level group (the fix in `47a909dfb` makes
   `LogisticsDisplayLinkedEntitySetupSystem` link route/start/end even when the arrow is already
   linked).
2. **Deferred-destroy re-link.** `LogisticsRouteDisplaySystem` (pre-transform group) unlinked the
   dying arrow immediately but recorded its destroy on the POST-transform ECB; a later system in
   between (`LogisticsDisplayLinkedEntitySetupSystem`, post-transform) saw a still-alive, now-unlinked
   arrow and re-linked it WITH its three dead children. Rule: **never link a set with a dead
   member** (unlink all of them instead), and treat "unlink now, destroy on a later ECB" as a
   window another system can re-link through.

**Keep the instrument.** `ControllerSystems/BlueprintPreviewGroupHygieneSystem` (ISystem,
`UpdateBefore(BlueprintPlacementSystem)`) prunes dead links from every live preview's group and
WARNS (`BlueprintPreviewGroupHygieneSystem pruned…`) — it is a tripwire in front of the
Instantiate, not a silencer: a warning in a run means a new writer broke rule 1 or 2. A defensive
prune INSIDE `BlueprintPlacerJob` was tried and reverted (nine `Tests.Blueprints.*Placement*` tests
threw a Burst NRE). Tests: `LogisticsDisplayLinkedEntitySetupSystemTest` (5),
`BlueprintPreviewGroupHygieneSystemTest` (3), `LinkedEntityGroupHygieneTest` (3). Record: 069 plan,
02:15 UTC PROGRESS block; RED/GREEN scans `repro5.out` / `repro7-green.out` in that session's scratchpad.
