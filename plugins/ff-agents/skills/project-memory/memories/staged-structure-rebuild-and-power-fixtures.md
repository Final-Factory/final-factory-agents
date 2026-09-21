---
name: staged-structure-rebuild-and-power-fixtures
description: "Destroyed staged structures need their construction marker restored; adjacent Standard structures do not share power without a connector."
---

# Rebuilding staged structures and proving power connections

Feature 074 T130: a Dark Star Gate was destroyed, rebuilt by construction bots, and supplied
with stage materials and ten probes. Its save still had stage 0, empty progress and no
`UnderConstructionTag`. Delivery alone did not prove stage processing.

`EntityConfigProcessor.ProcessConstructionConfig` bakes a default `ConstructionTracker` for
staged items. Normal placement adds `UnderConstructionTag` in
`BlueprintInstantiatorSystem.OnUpdate`; `ConstructionSystem.OnCreate` requires that tag and
`ConstructionJob.Execute` removes it on completion. The destruction path instantiates a fresh
prefab in `PlaceableDeletionSystem.PlaceableDeletionJob.Execute`, so it must add the tag when
`ConstructionConfig.StageCount > 0` too. It starts again at the prefab's stage 0; copying the
old completed tracker would skip the rebuild. Regression:
`DestroyedStructureGhostCadenceTest.DestroyedGhost_RecreatedStagedBuildingRestartsConstruction`
(cases 0, 3, 5). Trace each creation path, then run the actual destruction/replacement system.

The same live test had an independent fixture error: five powered chests directly beside the
gate did not power it. `StationConnectionsSystem.IsConnectionValid` rejects Standard-to-Standard
connections. The fixture needs compatible Connector links. Inspect the consumer's actual power
satisfaction and construction stage, not only a nearby provider's output or a resolved grid.
A corrected blueprint is still a proposal until live connection and processing are observed.
