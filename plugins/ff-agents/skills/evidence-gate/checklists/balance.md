# Balance changes: the difficulty curve before and after (w1440)

Ben, 2026-10-17: "late game balance seems really off right now ... you need to figure out how you can autonomously and
intelligently figure out game balance for a smooth difficulty curve throughout the game". Build 108 shipped camp
expansion's numbers with no run on a big late save, and a player's base met about three raids a second (w1439). The
game repo now measures the curve: `Documentation/Balance-Curve.md` is the target and the baseline, and the nightly's
`BAL-*` stages judge it (the light ones every night, the heavy saves on their weekdays). A stage plays its save at the
saved spot, then moves the player to the factory's most exposed edge (`ffauto:enemy.frontier`) and plays it again: a big
base's parked player meets no camp at all, and its edge is where the Build 108 runaway was.

**For any pull request that changes enemy, combat, spawn, economy or research numbers**: `GlobalConfig.asset`
(combat settings, curves), a weapon or enemy unit, spawner or turret asset, `FFSystems/EnemyAttacking`,
`FFSystems/EnemyCamps`, `CombatSettings.cs`, research costs or crafting rates that change how fast a base grows.
`pr_evidence.py` fails one that touches the enemy, combat or spawn paths without a `## Balance` section.

1. **Run the stages on both sides.** Build a development player of the base and of your branch
   (`scripts/nightly/build_player.sh`, cached by commit), then play the balance stages on each through the nightly
   runner, which leases the player slots (never launch a build from its folder):

   ```bash
   FF_NIGHTLY_HISTORY="$TMPDIR/bal-<side>/history" python scripts/nightly/ffnightly.py run --sha <sha> \
     --player <build>/player/finalfactory.exe --scenario BAL-early-economy --scenario BAL-mid-lifeastwo ... \
     --no-retry --jobs 3 --lab <a copy of lab.win.json with another port> --out "$TMPDIR/bal-<side>-$(date +%H%M%S)"
   ```

   Run the two sides one after the other from one sandbox: each run takes both of the sandbox's player slots, and the
   second refuses to start (`player_slots.SlotRequired: ... no free player slot`, w1465, 2026-10-20). A light stage
   (BAL-mid-lifeastwo) took 4.3 and 6.8 minutes there. Copy the lab fixtures (`<nightly history>/fixtures/w1440-*.zip`) into your history folder's `fixtures/` first. A
   leg costs 7 to 17 wall minutes on the light saves, about 40 on MeltCPU and over an hour on Just Play (three lanes on a
   busy lothdesktop, measured, w1440), so name the stages your change can move: a change that reaches one band runs that
   band's stages and one neighbour on each side, and says which; anything that touches late raids runs
   `BAL-end-justplay`, the save the runaway was reported on.
2. **Paste the table.** `python scripts/nightly/balance_lane.py compare <before stage dir> <after stage dir>` for each
   stage, and `balance_lane.py curve <run dir>` for the whole curve (the smoothness line). The section:

   ```markdown
   ## Balance

   Stages: BAL-mid-lifeastwo, BAL-end-justplay on players of <base sha> (before) and <branch sha> (after)

   | metric | before (BAL-end-justplay-frontier) | after (BAL-end-justplay-frontier) | after / before |
   ...

   Flags: <the lane's flags on the after build, or none>
   Baseline: <which stage baselines in scripts/nightly/balance-curve.json moved, and why; or unchanged>
   ```

   A change that cannot move the curve (log lines, a refactor proven equal) writes `No curve change: <why>` instead,
   with what proves it.
3. **A flag on the after build is a stop.** Fix it, or show it is the intended new curve: then move that stage's
   baseline (and a band bound only with the person's words for it) in the same pull request, and label each new number
   measured, sourced or a guess in `Documentation/Balance-Curve.md`.
4. **A design-level change is the person's call.** Bring the before/after curve as options with a recommendation;
   fix without asking only what is clearly a bug (a mechanism flag: raids beyond the launch schedule, a raid above
   the ship limit).
5. **After it merges**, the next night's `BAL-*` stages are the first check: read them in the night's report, and
   compare with your after table. Far off: stop and find why before anything else changes.

The fast EditMode pins (`EnemyPressureCurveTest`) still run in CI on every pull request. They pin the raid mechanics
on a synthetic base; the stages measure real saves, with expansion, rebuilds, garrisons and defenses in the loop.
