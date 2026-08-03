---
name: player-domain-already-conventional
description: "Architecture verdict: the proposed conventional-player/factory-lockstep split already exists. Determinism consumes player position through once-per-heartbeat fixed-point SimulationPosition adoption; presentation rate is the actual 057 problem."
metadata:
  node_type: memory
  type: project
  modified: 2026-08-02
---

# Player domain is already conventional

Final Factory already replicates the player conventionally rather than lockstep-simulating the
player transform. The local client reports its float presentation position through RPC; the host
produces a heartbeat snapshot; every peer adopts that snapshot as fixed-point
`Player.SimulationPosition`. Deterministic consumers read that fixed-point boundary rather than the
rendered transform (`Assets/Scripts/PlayerController/PlayerEntitySyncRpcController.cs:105`;
`Assets/Scripts/FFNetcode/GameManagement/GameStateRpcManager.cs:244`;
`Assets/Scripts/FFSystems/Player/PlayerSimulationPositionReplicationOps.cs:48,61-64,120-152`;
`Assets/Scripts/FFComponents/Player/PlayerAuthoring.cs:11-24`).

This means the 16 UPS feel problem does not require "un-lockstepping" the player. Replication and
presentation rate are separate concerns: the replication boundary already exists, while visible
player-adjacent movement still needs per-frame presentation.

Apply this rule when designing follow-up work:

- Preserve `SimulationPosition` plus the network-operation queue as the deterministic boundary.
- Never feed an interpolated or predicted float presentation value back into simulation.
- A future simplification may move local-player root integration to per-frame presentation while
  keeping the simulation contract unchanged, but it requires paired `SimulationPosition`
  bit-identity proof (`specs/057-unified-rate-smooth-presentation/tasks.md`, T012/T028).
- Combat remains the open domain decision because turrets and enemies cross simulation ownership
  boundaries. Decide it from measured event volume and cross-peer fingerprints, not by assuming the
  entire player domain needs migration (`specs/029-player-combat-lifecycle/research.md:151-156`;
  `Assets/Scripts/FFSystems/Multiplayer/DeterminismStateFingerprint.cs:5153-5161` identifies the
  player-position fingerprint surface).

Related: [[project-unified-16ups-smooth-presentation]].
