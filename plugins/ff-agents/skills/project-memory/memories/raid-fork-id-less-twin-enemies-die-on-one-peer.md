---
name: raid-fork-id-less-twin-enemies-die-on-one-peer
description: "w214 (2026-10-02), OPEN: the mid-fight raid fork with one enemy fewer on the host. Two enemy wanderers with no DeterministicCombatObjectId stand on one exact pose; a hit goes whole to one of them and their tie keeps archetype order, which a peer that loaded need not share, so one twin dies on the host only. Repro MP-trailer-raid-join-recovery; how to see it in a witness pair."
---

# The raid fork: id-less twin enemies, one dies on one peer only (w214, 2026-10-02, open)

**Symptom.** In a raid, 550-870 heartbeats after a mid-fight join: `vision+census` (sometimes `movers+`). One
enemy fewer in Chase on the host (`sig FC0931E2EB1363D1`), player Krillos/Bats idle on the host and in Chase on
the client, projectiles ±1-2. Desync board round 3f ("host one wanderer behind"), session 4 ("a wanderer with
`DeathMarker` on the host only") and w181's mid-fight forks look like the same thing.

**What the witness shows** (`-ffCombatFloatWitness` on both peers, `scripts/audit/compare_float_witness.py
--epoch 1`): "first heartbeat where the unkeyed records differ as a set", with a pair **0.000000000 apart**. Two
enemies with no object id share one exact pose and are bit-identical in every field for hundreds of heartbeats
on both peers. Then, on one peer, one twin's `targetTime` and `knnCollisionForce` stop updating (it has a
death marker), and the next heartbeat it is gone and its twin's enemy count drops. On the other peer both live.
Trace the twins by the peer's own entity key, not by position.

**Candidate cause (code read, not proven).**

- A projectile's hit goes whole to one candidate (`KnnProjectileCollisionSystem` → `KnnVisionSelect.ArgMin`).
- An exact tie keeps arrival order (`KnnVisionSelect.cs`, the RESIDUE paragraph).
- A source with no id, no pending identity and no grid tile is keyed by its raw position bits
  (`KnnSourceOrder.TierPositionOnly`, documented "NOT INJECTIVE ... archetype order again").
- So two twins tie, and which one is hit depends on archetype order. A peer that loaded need not share that
  order, and the twins' Health can already differ.
- Twins come from `EnemyShipSpawnerSystem`: positions rolled on tiles with a grid check ships are not in, no
  formation index. A spawner station with no identity (pre-055 saves, `terrain.place`) spawns unstamped ships.
- Proposal: identify every spawner station so its ships are stamped, and heal existing id-less twins on the
  host before a snapshot is served. `DeterministicCombatObjectId` is `[Save]`, so this needs an UpgradeStep and a
  fixture. A consumption-side rule cannot separate bit-identical records.

**Repro.** Nightly `MP-trailer-raid-join-recovery` (ledger `W214`). It forked in 3 of 4 runs on PR #924's build
and 2 of 2 on unmodified 0.50.0.64. With the host's fleet aggressive before the join it forked in none of 3.
The original `MP-trailer-raid-fleets` does not fly the fleets into the camp and stayed clean over 5,511
heartbeats.

Related: [[hidden-ship-stale-knn-vision-forks-host-vs-joiner]], [[two-peer-pair-lab-beast-and-m3-traps]],
[[order-sensitive-vision-buffer-consumers-open]].
