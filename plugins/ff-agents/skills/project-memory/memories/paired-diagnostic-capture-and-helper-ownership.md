---
description: Verify positive diagnostic capture on both peers early, and give each delegated peer separate helper filenames in the shared workspace.
---

# Paired diagnostic capture and helper ownership

Before a long diagnostic replay, write a checkpoint on every connected peer. Verify the
anchor is latched to the intended shared block, each requested surface has positive captured
records inside its window, and omissions/overflow are zero. Matching config declarations and
green fingerprints do not prove detailed capture ran. If any peer captured zero, fix or
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

## Three-peer capture: select the intended epoch

Pre-T133 guidance to join the investigated client last was a workaround for an explicit later
epoch being consumed by an earlier block. Since FinalFactory `f0a59a878`,
`ObserveHeartbeatForDiagnosticAnchor` ignores a new block whose epoch differs from a nonzero
`DiagnosticEpoch` and latches the selected epoch's next block. An epoch of zero remains
unspecified: it still latches the first eligible block. A later block still closes an existing
capture. This does not detect a full peer set automatically.

Feature074 T69 used host → BEAST → M3 with CampsDetail and AttacksDetail at epoch2 HB1–5000.
All three live peers latched epoch2 HB1. CampsDetail and AttacksDetail had positive captures with
zero omissions; the 159 shared heartbeats had matching authoritative fingerprints and raw times.
The run intentionally stopped after anchor and budget measurement, so it is not P6 acceptance.
Evidence: `ff-audit-artifacts/074-20260921/t69-early-artifacts/parent-verdict.json`.

Budget from the M3 T69 report: CampsDetail emitted three records per heartbeat
(`AttackScheduleDetail`, `CampOccupancyDetail`, and `CampsDetail` in
`DeterminismFingerprintSystem:808–841`). Its 477 records across 159 heartbeats used 34,587,787 B:
about 217,533 B per heartbeat, or about 1.087 GB over 5,000 heartbeats. Do not project from
bytes/477*5000. Measure both the heartbeat span and records per surface, then budget events:
HB1200–3500 spans 2,301 heartbeats and therefore produces 6,903 CampsDetail records.

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
