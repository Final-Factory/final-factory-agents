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
