---
name: verify-an-area-hazard-by-approaching-it
description: To verify a pull, aura or kill zone, approach it from outside under the player's own movement; spawning it on top of the player skips the collider that stops a ship at its edge (w1011)
---

# Verify an area hazard by approaching it from outside (w1011, 2026-10-11)

Ben: "apparently the black hole no longer sucks in the player and player ships and destroys them". Every first check
said it worked: the editor (Burst off and on, after a save load) and a built player each pulled the player in and
killed it within two seconds. All of them spawned the black hole 250 units from the player with the `spawnBlackHole`
cheat, already inside the hole's solid 300 `SphereCollider`.

The two-peer audit (`scripts/audit/run_black_hole_audit.sh` in the game repo) had the host FLY at a hole 600 units
away. It stopped dead at x = 298.7, 304 from the centre: the collider stops a ship under its own power
(`LinearMotionStep.Move`'s world raycast), and U16 (61238c1e2) had moved the pull to 300, so an approaching ship was
never pulled. Only the pull, applied with no collision check, carries a ship through the wall; the old 400 pull did.
Fix: PR #1477 (pull 350, death 150).

**How to apply:** for any zone effect (black hole pull, aura, slow field, damage ring), the check that counts is a
unit arriving from outside by its own movement, the way a player meets it. Spawning the zone around a waiting unit is a
second check, not the first. Read the zone's colliders (`grep -n "Collider" <prefab>`) and compare their radius with
the effect's range, at the unit's flying height (ships fly at `CrafterUpdateSystem.FleetY`, 40). Make the run fail
when nothing happens: w1011's audit gates on the host player being defeated, which is what caught a run whose
fingerprints matched perfectly while the player sat at the wall.

Related: [[windows-built-player-driving-traps]]
