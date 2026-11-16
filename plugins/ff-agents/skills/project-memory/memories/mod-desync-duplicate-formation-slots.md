---
name: mod-desync-duplicate-formation-slots
description: "A mod's multiplayer desync after a join or recovery (w4262, Cruiser): ships created with a duplicate FleetShip.FormationIndex are renumbered on load only, so client and host seed the movers differently. How to read it from FleetInputsDetail, the fix, and how to run a modded pair check (build, scenario traps, how many runs prove it)."
metadata:
  node_type: memory
  type: project
  modified: 2026-11-16T18:30:00Z
---

# A mod's desync: duplicate formation slots (w4262)

**The cause (measured, BEAST Intel host + LothDesktop AMD client, master 8cbfdcc630, Cruiser 2.0.0.2 cb47fdb).**
Cruiser created its carrier squadron ships with `FleetShip.FormationIndex` left at 0, so all of one carrier's fighters
shared slot 0. `FleetFormationIndexRestorationSystem` renumbers duplicate slots only when a world loads: a joining or
recovering client loads one, the host does not. The slot feeds `FleetShipDeterministicIdentity.GetStablePerShipHash`
(`FleetShipDeterministicIdentity.cs:69`), which seeds the overlap knock-out angle (`UnitOverlapPreventionSystem.cs:326`)
and the wander (`WanderSystem.cs:464`). The movers fork 8 heartbeats after every serve, and the client gets kicked
(the verdict said "env"). This has nothing to do with the `fp-combat-movers` toggle.

**How to see it.** The desync report's `FleetInputsDetail:` line gives `objectId= config= formation= owner=` for each
ship, once in the host's half and once in the client's half (split on `=== The client's half`). Group the ships by owner
and count the slots. In w4262 the host had Hornets 61, 62 and 64 (config 229) of carrier 21 (config 235) all on slot 0;
the client had no duplicates. The only digests that differed were those ships' positions and headings.

**The fix (Gherik1/Cruiser#3, never merged by us).** Every ship the mod creates takes the lowest free slot in its
owner's `OwnedShip` roster, as the game's own `ExecuteShipSpawnCommandSystem.ClaimFormationIndex` does. Suspect the
same in any mod that creates `FleetShip` itself. A game-side guard against duplicates was handed up as a follow-up.

## Running a modded pair check

- **Building the mod.** Run `ModDescriptionGenerator.UpdateAll` first, then `ScriptBatch.BuildGameWithBurst` under
  `unity-slot run`. Copy only the game's 7 DLLs into the mod template, never the rest of Managed.
- **Mod verbs in MP.** Cruiser routes mine, refit and spawnBoss through a building, so place one first.
- **Fighters need kills.** Carriers build Hornets only from scrap, and scrap only drops from kills. An idle repro with no
  enemies has no fighters and proves nothing.
- **Enemies.** On a flat map, Bats and Knights destroy the placed spawners quickly.
- **Verbs refused after a join.** `ffnightly` refuses LOCAL-only verbs (`desync.inject*`) once a client has joined, so
  plan probes before the join.
- **One clean run proves little.** The fork needs duplicate fighters overlapping at a serve: it showed in 1 of 3
  unpatched runs. Read the cause from the report, and run the fixed build more than once.

## A lone host with a client by address, no relay (w4462, 2026-11-16)

Measured on PR #3741 (253c947): LothDesktop hosted with ffnightly, and a worker on biscuit joined a Linux client by
Tailscale address.
- **A squadron with no enemy camp.** `ffauto:spawn.ships|Cruiser|3`, then `ffauto:enemy.leechspawner|25` on a flat
  map with `enemies: false`. The first Hornet launched 1.5 to 5 min later; wait with `logPresent` on
  `[FleetFormationIndexHeal] Renumbered`. `enemy.leechraid` was refused there ("no enemy camp").
- **The port is the lab's port + 1.** ffnightly bound 7965 for a lab port of 7964. Read `host-ready: port=` in host.log,
  or run `netstat -ano -p udp`, before you send the client the address. Cycle 1's first join failed on this.
- **Count by epoch, not heartbeats.** Each serve restarts the heartbeat count at 0 (`[SaveCapture] ... heartbeat=0
  epoch=N`). A `heartbeats` step across a rejoin ended at once, and the next step met a paused host.
  - Poll `ffauto:desync.stats` instead: `data.clients[0].compared` (one comparison per 8 heartbeats), then
    `data.epoch` for the rejoin.
  - A poll's `timeoutS` did not end the wait in this run (it was still waiting after 15 min with a 600 s timeout).
    Stop the run yourself once the numbers are in.
- **ffnightly hosts run `-batchmode -nographics`** unless the scenario sets `"windowed": true`.
- **A windowed Linux client on a locked screen falls behind.** XWayland gives it one-second frames
  (`HiddenWindowVSync.cs`), and the host drops it with `FlowControl:TooSlow` after about 5 to 7 min. Run that client
  `-batchmode -nographics`.
- **A client's default `PostConnectDelayMs` (1.5 s) ends its session** just after it joins. On a rejoin that shut the
  transport down. Pass `-ffAutomationPostConnectDelayMs 900000` and close it on your own timer.
