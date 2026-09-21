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

## Three-peer capture: put the investigated client last

The anchor closes when its heartbeat block ends; an epoch0 declaration does not reopen it
after another join or recovery (`NetworkDeterminismAudit.ObserveHeartbeatForDiagnosticAnchor`,
`ShouldCaptureDiagnostic`). In a three-peer replay, the first client can anchor to epoch1 and
lose detail when the third player creates epoch2. Join the comparison client LAST, then verify
positive detail on it and the host before replaying the action. Treat the first client's later
full fingerprints separately; do not claim it has detailed coverage just because its config matches.

Feature074 t18 (2026-09-20) used host → BEAST → M3, diagnostic epoch2 hb0–6000 with CensusDetail
and DirectionsDetail. Both host and M3 had positive epoch2 detail. At the first fork hb1261,
their CensusDetail rows isolated two Landing Zone signatures differing only by OutOfPlay.
Earlier t14 rejoin fingerprints remained complete, but detail ended when the anchored block
closed; those post-rejoin fingerprints never established post-rejoin CensusDetail coverage.
Source/evidence: FinalFactory specs/074-three-peer-full-playthrough/tasks.md T115/T116;
`NetworkDeterminismAudit.ObserveHeartbeatForDiagnosticAnchor` and
`DeterminismFingerprintSystem` CensusDetail producer. Preserve strict verdict limitations: the
untyped diagnostic rows are rejected by the strict verification parser, so this is attribution
evidence, not an acceptance pass.

## Capacity and persistence (074 T57, 2026-09-21)

The broad CensusDetail + MoversDetail + ProjectilePipelineDetail capture produced a
533 MB Windows checkpoint by heartbeat171 and a 1.03 GB host final report by heartbeat283.
M3 had about2 GiB free, failed publication with disk-full, and disconnected before gate
placement. Its swap use reached3 GiB. No gate conclusion follows from that run.

Use the narrowest useful surfaces and a short scheduled window around the action. Measure
actual bytes before extending the window; account for log/report copies and memory pressure.
Do not print whole matching diagnostic lines: one line can contain megabytes of entity data.
Parse selected fields and bound output instead.

A subsequent M5 restart removed the scratch run directory, including copies archived there
from peers. Persistent game-data reports and the peer builds had to be recovered. Keep the
sole evidence archive outside temporary storage before removing any peer original; follow
the [fleet evidence and capacity rules](feedback-prove-over-live-networked-machines.md).
