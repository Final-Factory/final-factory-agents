# Measuring an inserter presentation cost: a synthetic field, not JustPlay

**Learned:** 2026-10-12, w1065 (the inserter glide effect, lothdesktop).

- **JustPlay has 5 Inserter Bots** (and 12 Cargo Barges) among 143,641 structures, counted in the editor after a
  DevLoadSave. It cannot show what thousands of inserters cost. Build a field instead.
- **A field that never goes idle:** lanes of Spawner Chest (spawns Silica Ore) -> inserter -> Trash Can, one tile
  apart along z (`{"item":"Spawner Chest","at":[x,z],"spawn":"Silica Ore"}`, the inserter at `[x,z+1]` `dir` 0, the
  Trash Can at `[x,z+3]`), lanes 2 tiles apart in x and 5 in z. The Spawner Chest powers the grid, the Trash Can
  destroys what it gets, so every bot carries for as long as the game runs. A powered Cargo Hold as the target fills
  and stops the bots.
- **The agent API refuses a request over 64 KB** (`the request body may be at most 65536 bytes`), and the
  PostReadyCommand rides the command line. A 200-lane block (600 structures) encodes to 7.6 KB with
  `scripts/nightly/make_blueprint.py`: place ten of them, 20 tiles apart in z, over the channel
  (`ffauto:blueprint.place|<code>|x|z`) for 2,000 inserters. `player.setposition` to the field's centre and
  `camera.zoom|300` puts about 600 on screen.
- **Compare a stage, not the frame:** with the player's 60 fps cap most runs sat at 17 ms whatever the variant, and a
  busy shared PC swings single runs by 6 ms. The perf probe's `PerfSummary` (`ffauto:perf.sample|40|20`) splits the
  frame into PlayerLoop stages: presentation systems run in `PreLateUpdate`, so divide that stage's total by
  `frames`, take the median of three interleaved rounds per variant, and drop the round that ran into a neighbour's
  load. w1065 result: 2.60 ms (toggle off), 2.53 (v2 model only), 2.89 / 2.90 / 2.95 (glide styles 1 / 2 / 3).
