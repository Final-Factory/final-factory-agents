---
name: remote-player-presentation-position-bug
description: FIXED & on-screen VERIFIED — host ship now renders on client, smooth/precise/no-jiggle. Three fixes (presentation space, remote-motion exclusion, per-frame presentation).
metadata: 
  node_type: memory
  type: project
  originSessionId: 69537de8-2b0c-445e-9fc8-0308c478a219
---

Investigation handoff doc: `Documentation/Remote-Player-Presentation-Position-Bug.md` (2026-06-20/21).

**Bug:** host player's ECS-model ship didn't render on the client when the host moved (host view showed both ships). Purely presentation — sim/determinism fingerprints agreed.

**Three fixes (all in working tree, verified on-screen in a paired ParrelSync run):**
1. `RemotePlayerProjectionVisibilityAuditSystems.cs` `Apply` — Option A parent-relative convert (world projection → parent-local) so the parented model's world == projection. Host ship visible (was flung to (X,80,-957)).
2. `LinearMotionSystem.cs` — added `.WithNone<RemotePlayerTransformProjection>()` to the motion query. Remote players were being locally integrated every frame by the variable-dt LinearMotionSystem on the client and the root ran away (X≈17718 vs SimulationPosition≈150); Option A inverting that fast/far/stale parent caused the jiggle. Remote peers are authoritatively replicated, not locally simulated.
3. `RemotePlayerPresentationTransformSystem.cs` — moved from `FFFixedPreTransformGroup` (8 UPS) to `FFControllerPreTransformGroup` (per-frame) so the model samples the smooth network-interpolated projection every frame (the runaway parent was previously masking this by smoothing between heartbeats).

Temp diagnostics reverted (`DeterminismFingerprintSystem.cs` + `FFSystems.asmdef` to HEAD). Fast tests 501/501 on host+clone. **Not yet committed.** `main.unity` still has unrelated automation leftovers (`_startMode:0`, `NetworkMessageMetrics:1`).

**Screenshot verification how-to:** set client Game view to Free Aspect first (`FinalFactory/Dev/GameView Free Aspect` via MCP `execute_menu_item`, see `Assets/Editor/DevGameView.cs`) or `manage_camera screenshot` returns blank. Run staggered-arm paired session (doc §7) with `ExitPlayModeOnComplete:false`. Probe via MCP `execute_code` (fully-qualify types — `using` is illegal in method-body context): err = |model.LocalToWorld − projection|, should be 0.

**Superseded by spec 002 (`specs/002-player-positioning/`), implemented 2026-06-21.** Proper two-channel architecture: simulation (`Player.SimulationPosition` fp3, heartbeat, never smoothed) vs presentation (NetworkTransform + new owner-written `NetworkVariable<Vector3> PresentationVelocity` on `PlayerDataController`; remote root extrapolated from world-space velocity + reconciled toward the projection by the rewritten `RemotePlayerPresentationTransformSystem`; model at local identity). Replaced the 3 exploratory fixes: removed Option-A `Apply`, kept the `LinearMotionSystem` remote exclusion, rewrote the per-frame system. The 90° velocity bug was the remote velocity being applied in a rotated frame; fixed by replicating + applying the owner's world-space velocity verbatim. Live-verified: host +X → remote vel (100,0,0), model err≈0.7 bounded, model local identity, 508/508 fast tests on host+clone.

Related: [[feedback_test_command]], [[unity-mcp-server]]
