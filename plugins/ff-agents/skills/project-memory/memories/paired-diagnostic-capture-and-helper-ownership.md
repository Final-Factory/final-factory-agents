---
description: Verify positive diagnostic capture on both peers early, and give each delegated peer separate helper filenames in the shared workspace.
---

# Paired diagnostic capture and helper ownership

Before a long diagnostic replay, write a checkpoint on BOTH connected peers. Verify the
anchor is latched to the intended shared block, each requested surface has positive captured
records inside its window, and omissions/overflow are zero. Matching config declarations and
green fingerprints do not prove detailed capture ran. If either peer captured zero, fix or
explicitly bound the capture gap before spending the full run on attribution.

The September 10 spawner replay configured C3VisionDetail and SpawnerArmDetail correctly but
captured no host details. Host bootstrap armed at epoch1 HB2, after the join boundary.
`NetworkDeterminismAudit.ArmDiagnosticCapture` only sets the armed flag;
`ObserveHeartbeatForDiagnosticAnchor` latches only when a new block starts, and
`ShouldCaptureDiagnostic` rejects an unlatched anchor. Arming late misses the whole block.
Do not repair this by treating the current heartbeat as the start or comparing unrelated blocks.

For the following two-player replay, the host-only TargetClientCount=1 setting deliberately
armed capture during the solo block before launching the client. The driver separately verified
the real two-player session and both post-join captures. This was a reported workaround, not a
fix to the bootstrap race or proof of any larger peer count. Keep the anchor contract intact.

Direct children share the local filesystem, including /private/tmp. A remote-host assignment
does not make its locally prepared helper files private. Assign distinct host-* and client-*
helper names and explicit file ownership in every peer brief. Never rewrite the parent's
checkpoint, watcher, screenshot or HTTP helper to adapt it for the other peer. Outputs must
also use peer-specific names. Return actual copied paths and hashes; the driver verifies them
before comparison or cleanup.

Evidence: FinalFactory specs/069-research-bot-physical-determinism/plan.md, September 10
spawner and C3-preview replay records. The corrected replay captured all 5,000 requested
per-spawner records on BOTH peers; the comparison found no differences.
