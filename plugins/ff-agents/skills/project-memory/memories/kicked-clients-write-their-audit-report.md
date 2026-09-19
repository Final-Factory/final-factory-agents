---
name: kicked-clients-write-their-audit-report
description: "A client kicked by DesyncRecoveryFailed auto-writes its determinism audit report (…/DeterminismAudit/network-determinism-audit-<runId>-<legId>-client.log under the player's persistent data dir on M3/BEAST); cp3.sh cannot reach a kicked peer, so fetch that file and run fielddiff.py per epoch — on 074 leg t6 it turned an evidence-less double kick into three separately shaped defects (1-hb apply residual, permanent post-recovery fork, survivor fork on a peer kick)."
---

# Kicked clients write their audit report — fetch it, do not re-run the leg (074 t6, 2026-09-19)

When both clients of a three-peer leg were kicked (`DesyncRecoveryFailed`, attempt budget
exhausted) before any checkpoint, `cp3.sh` produced only the host report (`audit.write` is refused
once a client is back in the menu, and its agent-control HTTP is gone). The evidence was on disk
anyway: every kicked client had auto-written
`network-determinism-audit-<runId>-<legId>-client.log` into its `DeterminismAudit/` folder —
M3 `~/Library/Application Support/Never Games/finalfactory/DeterminismAudit/`, BEAST
`C:/Users/rydin/AppData/LocalLow/Never Games/finalfactory/DeterminismAudit/` (scp from BEAST with
the `C:/…` path form). Both hold the continuous per-heartbeat `Fingerprint` records for every epoch
the client lived through.

`python3 fielddiff.py HOST_REPORT KICKED_CLIENT_REPORT EPOCH | grep -v "all .* match"` per epoch then
gives the exact fork heartbeats. On t6 it separated what the host log alone had merged into "census
verdict → kick": epoch 2 unequal at EXACTLY hb 1768 (the apply heartbeat of a remote-applied Mining
Station placement, healed at 1769 — the same 1-hb residual as t5 hb 1027, which DISPROVED the
`TerrainItemFinderMarker` strip as its cause; it verdicted only because 1768 landed on the 8-hb
sample), the client's two recovery epochs unequal on EVERY heartbeat from hb 1 (the served snapshot
never matches the host's live world once the station exists — T108), and the OTHER client, never
recovered, equal through those epochs and then unequal from hb 1 of the epoch that began when the
first client was kicked (T109). Three defects, one leg, no re-run.

Also in [[built-pair-lab-traps-2026-09-18]] (the report's existence); this entry is the workflow.
