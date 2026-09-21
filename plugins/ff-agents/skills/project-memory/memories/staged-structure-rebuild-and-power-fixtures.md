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

Feature 074 T67 fixture lessons: `StationConnectionsSystem.IsConnectorConnectionValid`
(`Assets/Scripts/FFSystems/Stations/StationConnectionsSystem.cs:756-768`) accepts a Standard
only on a connector's Input or Output; its Perpendicular side requires a Connector. Inserting an
Up connector beside a Standard chest alone therefore does not make a valid connection. The live
successful geometry used gate anchor `(-955,564)`, Up connectors at x `[-952,-948,-944,-940,-936]`,
z `563`, and Standard chests at the same x positions at z `562`; the live consumer reported
`power.satisfaction=1`.

`ConstructionTaskAssignerSystem.TryProcessPlayer`
(`Assets/Scripts/FFSystems/ConstructionBots/ConstructionTaskAssignerSystem.cs:246,265-278`) measures
the placeable's `CenterTile` against the integer tile from `PlayerSimulationPosition`, using the
circular range `ActionRange / 10`. A near corner or anchor does not establish that construction bots
can reach the task.

`transfer.put` reports the requested count because
`LocalMultiplayerAutomationCommandRunner.ExecuteTransferPut` only dispatches the request; the bake in
`InventoryTransferOutcomeBuilder.TryBakeTransfer` clamps it to source availability and target capacity.
The gate accepts only a small connector inventory, so space transfers across heartbeats and prove
actual stage progress with the production reader rather than command status. T67's initial request
for 25 engines delivered 8; later spaced transfers delivered the remaining 17 and proved stage 1.

Use an assertion tolerance at least as large as the preceding `movement.goto` completion tolerance:
`goto` at 12 followed by `assertnear` at 10 can reject a normal completed arrival; use 20 here.
