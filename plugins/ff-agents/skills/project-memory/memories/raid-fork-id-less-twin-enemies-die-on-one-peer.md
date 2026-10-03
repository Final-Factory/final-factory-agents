---
name: raid-fork-id-less-twin-enemies-die-on-one-peer
description: "w214/w215 (2026-10-02), FIXED by PR #938: the mid-fight raid fork with one enemy fewer on the host. Two enemy wanderers with no DeterministicCombatObjectId stand on one exact pose; a hit goes whole to one of them and their tie keeps archetype order, which a peer that loaded need not share, so one twin dies on the host only. Repro MP-trailer-raid-join-recovery; how to see it in a witness pair."
---

# The raid fork: id-less twin enemies, one dies on one peer only (w214/w215, 2026-10-02, fixed by PR #938)

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

**Proven (w215).** `-ffTwinProbe <file>` (`TwinEnemyProbeSystem`) + `scripts/audit/compare_twin_probe.py` name the first
shot that lands on a different twin: one projectile hit the 27-health twin on the host and the 24-health twin on the
client, both peers listing the pair in the SAME chunk order. So it is not chunk order alone: `KnnSystem` sorts its
sources with an unstable `Sort()` on the key only, and the twins' order follows the whole gather layout.

**Fixed (PR #938).** `CombatIdentityHealSystem` stamps every spawner station with no identity (keyed by its grid tile)
and every id-less enemy ship in an identified owner's roster (owner id + next spawn ordinal, in SAVED ROSTER ORDER, which
every peer shares), on every peer in the same heartbeat. `AggroSystem` ties shooters by the KNN source key. A ship
with no owner roster stays id-less (logged `IdlessEnemyResidue`): twins can differ only in who targets them, so no
per-peer rule can name them alike; only a single-peer mint (the host's load migration) can.

**The cause as first read from code:**

- A projectile's hit goes whole to one candidate (`KnnProjectileCollisionSystem` → `KnnVisionSelect.ArgMin`).
- An exact tie keeps arrival order (`KnnVisionSelect.cs`, the RESIDUE paragraph).
- A source with no id, no pending identity and no grid tile is keyed by its raw position bits
  (`KnnSourceOrder.TierPositionOnly`, documented "NOT INJECTIVE ... archetype order again").
- So two twins tie, and which one is hit depends on archetype order. A peer that loaded need not share that
  order, and the twins' Health can already differ.
- Twins come from `EnemyShipSpawnerSystem`: positions rolled on tiles with a grid check ships are not in, no
  formation index. A spawner station with no identity (pre-055 saves, `terrain.place`) spawns unstamped ships.
- A consumption-side rule cannot separate bit-identical records; only an identity can. No UpgradeStep was needed in
  the end: the heal adds components that are already `[Save]`, at runtime, on every peer.

**Repro.** Nightly `MP-trailer-raid-join-recovery` (ledger `W214`, closed). Before the fix 7 forks in 9 runs; after,
no verdict in 10 of 10 across Mac + Mac, Windows + Windows and Mac + Windows. With the host's fleet aggressive before the join it forked in none of 3.
The original `MP-trailer-raid-fleets` does not fly the fleets into the camp and stayed clean over 5,511
heartbeats.

Related: [[hidden-ship-stale-knn-vision-forks-host-vs-joiner]], [[two-peer-pair-lab-beast-and-m3-traps]],
[[order-sensitive-vision-buffer-consumers-open]].
