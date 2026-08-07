---
name: add-network-operation
description: Add a new gameplay mutation (network operation) to Final Factory's deterministic lockstep pipeline - the request/completed op pair, host-side validation, payload baking, broadcast, and the single-player shared path. Use when adding ANY new gameplay state mutation, when wiring a client intent to authoritative state, or when tempted to mutate simulation state from a direct ClientRpc (never do that - it races the heartbeat and desyncs).
---

# Adding a network operation (the right place for gameplay mutations)

Full recipe behind the game repo CLAUDE.md's network-operations kernel (moved here by
feature 061). These are crown-jewel surfaces — see `Documentation/Crown-Jewel-Surfaces.md`
for who may edit what; the driver owns the design.

## The one ordered queue path

There is ONE ordered queue path, shared by single-player and multiplayer —
`NetworkOperationQueues` (`Assets/Scripts/FFCore/Network/NetworkOperationQueues.cs`):
`ClientRequestQueue` (client → host intents) and `OutboundOperationsQueue` (host → every
peer, **and the channel the heartbeat itself rides**). `HeartbeatSystem.PerformSystemUpdate()`
runs every engine frame and drains them in order:

1. `ProcessClientRequests()` — host dequeues `ClientRequestQueue`, validates each request, and
   authors the resulting authoritative event.
2. `PerformQueuedOperations()` — every peer dequeues `OutboundOperationsQueue` and applies each
   op via `NetworkOperationPerformer`. **The heartbeat is itself a queue entry**: when a
   `Heartbeat` op is dequeued, the system adopts the carried player positions, increments
   `Heartbeat.CurrentHeartbeatFrame`, and `return`s. Consequences: every non-heartbeat op ahead
   of the heartbeat is applied *before* the increment (so fixed-step systems see it on that
   heartbeat), and **at most one heartbeat advances per engine frame** (backlogs catch up
   one-per-frame, never collapsed).

The only single-player vs multiplayer difference lives in `HeartbeatSystem.PublishHeartbeat()`
— multiplayer host sends `DoHeartbeatClientRpc` `SendTo.Everyone` (so the host receives its
own heartbeat back through the same ordered channel as ops); single-player enqueues directly.
Everything else is identical, so there is one code path to keep deterministic.

## The recipe

Do NOT mutate simulation state from a direct `ClientRpc` — that races the heartbeat and
desyncs. Instead:

1. Add a `NetworkGameOperationType` (`FFCore/Network/NetworkGameOperationType.cs`) — typically
   a request + a completed pair.
2. Client submits the request via `GameStateRpcManager.IncomingClientRequestServerRpc(...)`
   (stamps the current `SessionEpoch`).
3. Add an `AbstractNetworkOperation` handler under `Assets/Scripts/NetworkOperations/` (see
   the mining operations at the folder root and `Blueprints/` for the template) and register
   it in `NetworkOperationPerformer`. The **request** handler runs host-side: validate against
   authoritative state, resolve ALL nondeterminism once (RNG, lookups), bake the outcome into
   a payload, and broadcast it via `GameStateRpcManager.DoServerCommandAllRpc(...)`
   (`SendTo.Everyone`). The **completed** handler runs on every peer and only *replays* the
   precomputed deltas — never re-rolls or re-validates.
4. Share the host's outcome-builder with the single-player path so results don't drift (see
   `MiningCompletedPayloadBuilder`).

## Boundaries

Direct `ClientRpc`s are allowed only for presentation-only effects (e.g. mining beam visuals);
the moment a gameplay system consumes their state as truth, migrate them onto an operation.
Remote-player network data must land in presentation projections
(`RemoteLocalTransformTarget` — consumed by the `RemotePlayerPresentation` step — and
`RemotePlayerInventorySlot`), never simulation-truth components.

Full contract: `specs/001-deterministic-multiplayer/spec.md` (FR-001..FR-006) and
`Documentation/Authoritative-Event-Envelope.md`. Verify any new operation with the
`determinism-audit` skill (paired audit) before calling it done.
