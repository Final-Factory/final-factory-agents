# Verify the player can act before interpreting playtest receipts

Observed in feature 074 T52, 2026-09-21: a movement chain completed while M3 was dead,
far from its target, and without construction bots. The following gate-placement command
reported six structures, but the saved gate was an OutOfPlay construction task and the
screenshot showed the death panel. The driver had overlooked health=0 in a prior snapshot.

`LocalMultiplayerAutomationCommandRunner.ExecuteMovementGoto` starts a separate asynchronous
movement drive and returns an estimated pacing delay. Its chain completion does **not** await
or assert successful arrival. Read the journal's `gotoResult`, then use
`player.assertnear|tileX|tileZ|radiusUnits` and a player snapshot before a dependent action.
`movement.goto` takes world coordinates; `player.assertnear` takes tile coordinates.

Before remote construction or interaction, check that the player's health is positive, no
death panel blocks input, the authoritative position is in range, the inventory holds the
needed items, and construction bots exist. Use the normal `combat.respawn` command if dead,
then verify the resulting health and position. Granting invulnerability does not revive an
already dead player. Recheck after long travel or combat.

`ExecuteConstructionPlace` reports the blueprint item count, not completed construction.
Verify the actual placed tasks, their completion, and the built structure's function before
counting an objective. Use a rendered machine's screenshot alongside structured snapshots;
never treat command acceptance, elapsed pacing, or a nonempty entity list as outcome proof.

If a failed prerequisite invalidates an attempted scenario, preserve it as diagnostic evidence,
state the coverage gap, and rerun with verified prerequisites. Do not retroactively claim the
attempt passed. Scope a desync to its actual trigger (for T52: blueprint placement while dead)
until a valid live-player reproduction establishes broader impact.
