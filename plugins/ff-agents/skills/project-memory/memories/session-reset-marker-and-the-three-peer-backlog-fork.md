---
name: session-reset-marker-and-the-three-peer-backlog-fork
description: "A join/recovery session reset used to clear EVERY peer's network queues at RPC receipt; a client drains at most one heartbeat per frame, so any third peer that was lagging dropped its un-applied backlog, kept its old world and restarted counting at 0 against a host k heartbeats ahead — a guaranteed fork, whose recovery reset the freshly served peer mid-catch-up (the cascade). Only reachable with 3+ peers; every two-peer lane is blind to it. Fixed 1bb8a9cb1: the host and every non-served client enqueue a SessionReset marker and apply the reset at its stream position."
---

# The session reset applies at its stream position; two-peer lanes cannot see the backlog fork (2026-09-12, 069 lane r13/r14)

- **The old mechanism (pre-`1bb8a9cb1`).** The serve path (`GameStateRpcManager.cs` `ServeSaveFileWhenHostReady`)
  paused heartbeats, advanced the epoch and sent `ResetHeartbeatOnEveryoneRpc` to everyone; every receiver
  called `HeartbeatSystem.ResetHeartbeat()` with its default `clearNetworkQueues = true` →
  `NetworkOperationQueues.Clear()`. A client applies at most ONE heartbeat per engine frame
  (`HeartbeatSystem.PerformQueuedOperations` returns after each heartbeat), so a peer that is behind by the
  flow-control lead (`FlowControl.cs:48` `LeadSeconds = 0.75` = 12 hb at 16 UPS) holds a backlog the host has
  ALREADY applied. The served peer's snapshot supersedes its backlog; every OTHER client lost it, kept its old
  world and restarted at hb 0 → verdict at the first sample → its own recovery → whose reset hit the previously
  served peer while it was still replaying its catch-up (paused) → cascade. Live RED (r13 t2, three peers,
  build `4aabc5d4a`): a 12-hb backlog dropped → 3 recoveries + 12 host signals from ONE forced resync.
- **Why nothing found it earlier:** with two peers the only non-host client is always the served one. Ben's
  Steam logs showed two remote players = three peers. Any desync class that needs a NON-served client cannot
  be reproduced on a pair — put a third peer (the clone editor is fine as the trigger peer) in the lane.
- **The contract now (`1bb8a9cb1`).** `ResetHeartbeatOnEveryoneRpc(uint sessionEpoch, ulong servedClientId)`
  (`GameStateRpcManager.cs:1153`): every peer adopts the epoch at receipt (later RPCs are stamped with it);
  the served client (`!IsServer && LocalClientId == servedClientId`) keeps the clear-now path; the host and every
  other client call `NetworkOperationQueues.EnqueueSessionReset(epoch)` (`NetworkOperationQueues.cs:64`,
  `NetworkGameOperationType.SessionReset = 60`, `NetworkGameOperationType.cs:253`) and the heartbeat drain applies
  `ResetHeartbeat(clearNetworkQueues: false)` when it REACHES the marker — everything queued ahead applies
  first, the new epoch's stream stays queued behind. The serve waits (≤5 s, audited `SessionResetApplyTimeout`)
  for the host's own marker (`Delegates.IsSessionResetApplied`, `GameStateRpcManager.cs:1023`) BEFORE the joiner's
  spawn and the snapshot, so the snapshot is taken exactly at the reset position. The runtime detector skips
  sampling while `NetworkOperationQueues.HasPendingSessionReset()` (`:76`) — a (newEpoch, oldHeartbeat) sample
  would be retained by the host as "ahead" and compared ~100 s later = a false verdict. The audit LABEL advances
  at the marker too (`SessionEpochTracker.AdoptDeferringAuditLabel`, `bdb6bdfc9`) so pre-marker heartbeats stay
  under their own epoch in reports. The new enum member changes the op-family hash: old and new builds refuse to
  mix at the 017 join gate, as they must.
- **Tests:** `HeartbeatCatchUpTest.NonServedPeerAppliesItsBacklogBeforeTheSessionResetAndKeepsTheStreamBehindIt`,
  `SessionResetMarkerIsNotACatchUpHeartbeatInTheResetSummary`,
  `DeferredAdoptionMovesTheEpochButNotTheAuditLabelUntilTheMarkerApplies`; `DefaultResetClearsBacklog` still pins
  the served-peer clear. GREEN (r14 t2, identical trigger): 0 verdicts, 1 recovery; comparator host-vs-A 3018 +
  1072 samples, 0 mismatches, INCLUDING the twelve backlog heartbeats applied under the pending marker.
- **Reading the audit:** the fix witnesses `deferredToMarker=true,backlogAhead=…` and `SessionResetApplied
  epoch=…,queuedBehind=…` are NON-critical records — absent from terminal logs and verification-profile reports;
  only the diagnostic profile carries them. Doc: `Documentation/Player-Position-Determinism.md` ("Every OTHER peer
  applies the reset at its stream position").
- Related: [[three-peer-lane-recipe-and-traps]], [[player-presentation-transform-forks-combat]].
