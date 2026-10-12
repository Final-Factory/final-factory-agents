---
name: nightly-e2e-tutorial-lessons-2026-10-10
description: "What building the nightly tutorial end-to-end test (w923, MP-tutorial-e2e-loth/-ben) taught, 2026-10-10: judge a UI flow from a per-frame trace the player logs itself (a poll at 4 Hz misses 0.3 s states), compare it with a golden step list rather than the build's own assets; a completed objective card leaves ObjectivesPanel's dictionary at once (enumerate the hierarchy to see its animation); one long frame moves Time.unscaledTime and breaks the card dwell/animation (read [MP pacing] max frameMs); unit.kill is single-player only and forks a 2-peer game; hand crafts eat Low/Medium Density Structures from the bag; inventory.add drops what does not fit; build_player.sh reverts tracked edits made mid-build; poke.py plus a shim replays a recipe against live players; two agents' lab runs clash on port 7890/7891."
metadata:
  type: project
---

Source: w923, `scripts/nightly/README-tutorial.md`, PR #1442. Companion to [[nightly-e2e-lab-lessons-2026-09-28]],
[[nightly-e2e-windows-lab-lessons-2026-09-29]] and [[nightly-e2e-chaos-soak-lessons-2026-09-29]].

**Judge the flow from a trace the player writes.** `TutorialTrace.cs` (`-ffTutorialTrace true`) logs one `[TutorialTrace]`
line per change of the objectives controller, the panel, the subtitle panel, `NarrationHold`, the arrows and the "technology
unlocked" popup, every frame; `tutorial_check.py` reads the logs offline. Polling the agent channel misses 0.3 s states and
cannot say when a card went. Judge against a committed golden list (`tutorial_definition.py write` from
`ObjectivesTryHard`), never the assets of the build under test, or a deleted step deletes its own expectation. Read private UI
fields by reflection in the trace: a test must not widen UI classes (a change under `/UI/` makes `pr_evidence.py` ask for UI
evidence).

**A completed card is not in `ObjectivesPanel._objectiveItems`.** `RemoveObjective` takes it out the moment its step completes;
the item plays its 0.9 s animation and is destroyed. Enumerate `_content.GetComponentsInChildren<ObjectiveItem>` and read
`IsCompleting` to see the animation.

**One long frame moves the game's clock.** Card animation, dwell and `NarrationHold` run on `Time.unscaledTime`: a 3.8 s frame at
the step-34 reveal made a step complete 0.05 s after its card appeared; a 0.67 s frame cut an animation to 0.25 s. The player's
`[MP pacing]` line carries `frameMs ... max=`; excuse a timing rule broken inside a window with a 400 ms or longer frame and report the
hitch.

**Driving a tutorial with ffauto.** Bauxite asteroid world centre = tile centre x 10; `mining.until` needs the ship within ~100
units; a mining or research station sits 13 tiles from an asteroid centre (placement tiles are re-anchored: read `GridTile`
back); `craft.queue` hand-crafts for real in seconds (ships too); `transfer.put/quicktake`, `setting.filteritem`,
`assembler.setrecipe` are the panels' own ops; `research.chain` then wait for the tech before crafting its unlock; Escape closes the
"technology unlocked" popup that covers the card (only when it is up: Escape alone opens the menu); the camp falls to the host's 4 Bats
and a Frenzy cast at it in ~10 s. `unit.kill` is single-player only: in a 2-peer game it forked both peers (desync reports).
A stray hand-crafted Miner Bot in the fleet starts a triggered card ("Get rid of the all the mining bots").

**Bag traps.** Connector and Solar Panel are made from Low and Medium Density Structures, so a craft after a top-up eats it: crafts
first, top-ups last. `inventory.add` drops what does not fit the bag (300 ore of each type lost later additions). A leftover item in an
assembler's one primary slot blocks the next recipe's input.

**Harness traps.** `build_player.sh` restores every tracked file the tree shows as changed when it ends, yours included: it undid two
edits to `ffnightly.py` and `coverage.json` made while a build ran (it now keeps `restored.patch`). Two agents' ffnightly runs on one
PC share lab port 7890+attempt: superseded (w1046 followed this line and ran beside another worker's run): the lab lock is the
machine's on purpose; retry `ffnightly.py run` every 30 s and never point `FF_NIGHTLY_ROOT` elsewhere (the `playtest` skill, "the lab is locked").
`poke.py up` plus a small shim that wraps its peers as a runner `run` object replays a step recipe against live players and leaves them
up after a failure.
