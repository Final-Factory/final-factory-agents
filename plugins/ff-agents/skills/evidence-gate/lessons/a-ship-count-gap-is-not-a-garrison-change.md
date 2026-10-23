# A balance stage's ship-count gap is not a garrison change until the mix says so (w1740)

**The rule.** When two builds differ only in what a few camps build late, a gap in `enemyShipsMax` (enemy ships
alive at their peak) between their `BAL-*` stage runs can be the different trajectory the changed camps start,
not weaker or stronger camps. Before calling it either, measure the garrison itself, on both arms:

1. **The built spawner mix and its capacity**: the camps' stations by item at the end of the leg, and the sum of
   each spawner's base `MaxCount` (Cutter 10, Stinger 15, Trident 20 on 2026-10-22) over them.
2. **Ships alive by type on a pinned timeline**: in the editor, fire the stage's ops at exact heartbeats from an
   `EditorApplication.update` hook (`ffauto:enemy.frontier` at the heartbeat the stage reaches it, `game.speed|8`) and
   count `Enemy` + `FleetShip` + `Health` entities without `DeletionMarker` by item every few hundred heartbeats.
   With the op timing pinned, master run twice gave identical camps building for building; without it, two runs of one
   build gave 17 and 21 Cutter Spawners.
3. **Against a third arm** (the pool before the change that started it), diff station by station, so a gap the
   earlier change made is not charged to yours.

**Why.** w1740 (2026-10-22): the camp-builder fix (FinalFactory PR #2192) read 95 against master's 134 peak guard
ships at the LifeAsTwo frontier on Mac players, each build repeatable run to run, and 504 against 541 on Trailer. On
the pinned editor timeline the same two arms gave peak 104 against 100, mean 45.3 against 48.8, and capacity 965
against 945: the camps were not weaker. The gap to the pool before #2173 (mean 67.9) was the 6 Leech Spawner slots
#2173 added, the same on master. The brief's stop rule ("if the numbers show the fix changes anything beyond restoring
the pre-#2173 mix, don't merge") held the PR for a person's answer that the measurement could have settled first.

**How to apply.** A `## Balance` section that reports an `enemyShipsMax` change from a change to camp building also
gives the mix, the capacity and the pinned-timeline counts for both arms, measured; the player stage's number alone
is a guess about the garrison.
