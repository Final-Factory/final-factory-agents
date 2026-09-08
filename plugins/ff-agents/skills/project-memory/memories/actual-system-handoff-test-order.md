# Actual-system handoff tests follow source group order

For a handoff test that drives the actual systems, arrange observations in their real fixed-group
order. `CombatMoverRailMirrorSystem` runs in `FFFixedPreTransformGroup`
(`CombatMoverRailMirrorSystem.cs:96-98`), while the test's `queuedShipTransferCommandSystem`
drives `ShipTransferCommandSystem` in `FFFixedPostTransformGroup`
(`ShipTransferCommandSystem.cs:30-31`): capture the Early snapshot before the next PreTransform
mirror. Seed the prior actual rail, execute the real handoff/playback, then observe the next Early
state. Do not add an impossible mirror merely to make a next-Early assertion pass; that hides the
stale-snapshot failure the test is meant to expose.
