---
name: agent-control-chain-fifo-and-mining-startnearest
description: "Agent-control command chains (`POST /v1/command`, `chain.sh`) are ONE FIFO per player: a chain submitted while another runs waits with a `queuePosition`, and a `flowcontrol.throttle|20|900` segment holds the queue for its whole duration -- the checkpoint's `audit.write` (cp.sh) queued behind it and the leg 'failed' with a missing host report until the throttle ended; there is no cancel route. `mining.startnearest|<range>` is the PLAYER's beam (MiningAction.BeginAutomationMining) and needs a Mineable+Placeable target within <range> world units of SimulationPosition -- f2's chain failed on it and f3/f4 never issued it, so no earlier leg had ever depleted the asteroid it claimed to mine."
---

# Agent-control chains are a FIFO; `mining.startnearest` is the player's beam (073, 2026-09-15)

**Chains queue.** `LocalMultiplayerAutomationCommandRunner` executes chains for a player strictly in
submission order. `GET chain/<id>` on a waiting chain shows `startedHeartbeat: -1, queuePosition: N`.
A long segment (`flowcontrol.throttle|fps|seconds`, `wait|seconds`, `flowcontrol.stall`) blocks
everything behind it. Consequences seen live:
- `cp.sh` → `checkpoint.py` → `ffauto:audit.write|<label>` sat behind a 900 s throttle; `cp.sh` printed
  a FileNotFound for the host report and the leg looked broken. The report was written when the throttle
  ended (`chain/<id>` → `result: "determinism audit report written: <path>"`); copy it then and compare.
- `chain/<id>/cancel` and `DELETE chain/<id>` are 405 -- there is no cancel. Only the most recent 32
  chains are retained.
Order a leg as: actions (spawn, goto, mining) → throttle LAST → checkpoint AFTER the throttle's end
(or poll the checkpoint chain until `completed`). Run the fps probe before the throttle segment if you
want to catch the cap in the probe, not just in the reports.

**`mining.startnearest|<range>`** (`LocalMultiplayerAutomationCommandRunner.ExecuteMiningStartNearest`):
finds the nearest entity with `Mineable` + `Placeable` + `LocalTransform` (not an activated
`ActivatableStructure`) within `<range>` world units of `PlayersManager.Me.SimulationPosition`, then
`MiningAction.BeginAutomationMining(target)` + `PlayerControllerState.Mining`. It is the player's own
beam, not a miner-bot order. From the player standing at tile (198,96) a `terrain.place`d Iron Asteroid
at tile (200,100) resolved at distance ~284 (world units), so `|80` fails and `|400` works. A 20-ore
asteroid was mined out in ~90 heartbeats with the beam + 2 Miner Bots in the fleet. Always read the chain
RESULT (`grep completed\|failed`) -- the earlier legs' "mines it out" claims were never checked and the
mining segment had failed with "could not find a mineable target within range 80".
