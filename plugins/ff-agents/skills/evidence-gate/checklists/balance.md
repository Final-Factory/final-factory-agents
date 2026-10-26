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

   Pass `--budget-min 300` on a hand run: the default budget skipped BAL-end-justplay after the other stages (w2039,
   2026-10-24). To stop a run, end the `ffnightly.py` process itself by its command line, not only the background shell
   that started it: `TaskStop` left the runner holding both player slots and `ff-leftovers list` did not show it
   ([the trap](../../project-memory/memories/batch-player-build-traps-switch-branch-and-ilpp.md)). Since w2039 the lane
   also judges attacks, camps and guards apart against `stages.<stage>.spread` (mean ± max(3 sd, 1), from three or
   more runs: `balance_lane.py spread`), and flags awake-ship growth as a performance signal; a curve change re-measures
   that spread too.

   **Where the saves are.** The `lab:` stages (BAL-end-justplay, BAL-late-lifesave, BAL-end-meltcpu: `w1440-*.zip`) need
   their lab fixtures, and BEAST has none (no `w1440-*.zip` anywhere under F:/ffw, checked 2026-10-20, w1243); the
   baselines were measured on lothdesktop. On another machine only the stages from repo or golden-fixture saves run as
   they are: BAL-early-economy, BAL-early-timtesting, BAL-mid-lifeastwo, BAL-mid-trailer. For the late band, run on
   lothdesktop or get the fixtures handed over as attachments (`publish_attachment`, `fetch_attachment`), and say in
   `Baseline:` which late stages you did not run.

   **A before player from your own sandbox** (w2183, 2026-10-26, BEAST): with your work pushed and the editor stopped,
   `switch_branch` to a scratch branch with `create_from` = the master commit your branch last merged, run
   `build_player.sh` there (about 10 minutes), and `switch_branch` back only after it prints `ok:` (switching while it
   runs builds the other branch: `batch-player-build-traps-switch-branch-and-ilpp.md`). Its Library is warm, unlike a
   fresh clone's. The three light stages then took 8.4 and 10.9 minutes a side with `--jobs 2`. Master can already flag
   against a stage's spread (w2183: lifeastwo and trailer flagged on both sides); compare flag counts, not pass/fail.

   **No before build.** When a before player cannot be built (w1243: the sandbox was held by another agent, so the
   worktree could not be switched to the base) and the after numbers equal the stage baselines in
   `scripts/nightly/balance-curve.json`, the baselines can stand as the before column. Label it with the baseline's
   commit, machine and date. An after number that differs from its baseline needs a real before build: the baseline's
   commit is older than your base. In w1243, radius 4 left raids per hour equal on early-economy and mid-lifeastwo: the
   launch schedule, not the activity gate, set the rate there.
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
3a. **A gap in enemy ships alive is not yet a garrison change** (w1740). When the change only alters what some camps
   build, give both arms' built spawner mix, its capacity, and ships alive by type on a pinned editor timeline before
   calling camps weaker or stronger: [the lesson](../lessons/look-early-by-breakdown.md#a-ship-count-gap-is-not-a-garrison-change-w1740).
4. **A design-level change is the person's call.** Bring the before/after curve as options with a recommendation;
   fix without asking only what is clearly a bug (a mechanism flag: raids beyond the launch schedule, a raid above
   the ship limit).
5. **After it merges**, the next night's `BAL-*` stages are the first check: read them in the night's report, and
   compare with your after table. Far off: stop and find why before anything else changes.

The fast EditMode pins (`EnemyPressureCurveTest`) still run in CI on every pull request. They pin the raid mechanics
on a synthetic base; the stages measure real saves, with expansion, rebuilds, garrisons and defenses in the loop.
