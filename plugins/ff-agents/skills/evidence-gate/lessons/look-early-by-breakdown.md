---
name: look-early-by-breakdown
description: "After anything goes live, the first check comes within hours, reads the breakdowns that would show each likely failure, and compares them with numbers written down beforehand. Totals cannot fail."
date: 2026-10-02
---

# Look early, by breakdown, against a written expectation

**Rule.** Before the action, write the three likeliest ways it fails and what would show each,
and the numbers you expect. Schedule the first check early. Read the breakdowns, not the total.
If reality is far off, stop and diagnose before changing anything.

**Why.** The Reddit campaign of 2026-10-01 was read at about +1 h, +3 h, +5 h and +13 h. Each
time the worker reported totals: "nothing looks wrong", then "well behind the pace". No expected
number had been written, so no check could fail, and each check happened because the orchestrator
asked. The first review had been planned for 48 hours in, by ad and ad group.

At 13 hours the caps were raised without a diagnosis. At 21.6 hours someone read the country
table: the two cheapest countries in the ad group had nearly all the impressions, and the US had
almost none. By then total spend was back on pace, so the total looked healthy while nearly all
of it went to the wrong countries.

The plan had also reasoned that a cap set too low "under-delivers, which costs nothing". In a
seven-day sale, each lost day is a seventh of the window.

**How to apply.**

- In the record: **fails if** (three failures, each with its signal), **expect** (numbers at the
  first check), **first check** (when, which breakdowns), and the result that means stop.
- Pick breakdowns that separate the failures: for ads, country, ad group and creative; for a
  release, version and platform; for a multiplayer fix, host and client.
- Use `wake_me` so the check happens when it is due, not when someone asks. A check that recurs
  (every hour, each morning) is an FF Factory orchestrator's `set_timer`, set once; `wake_me` is
  one-off and a person's message cancels it.
- A check that returns totals only is incomplete. Say so and read the tables.
- Off the numbers: pause what is off, name which failure it is, report. An adjustment is a new
  decision with its own basis.
- For ads the first check is within 2 hours and the tripwire is half the expected pace. Ben
  accepted both as starting values on 2026-10-02; they are settings in ff-marketing's `ffads`.

## A ship-count gap is not a garrison change (w1740)

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
