---
name: map-gen-regime-must-match-across-peers
description: MapGenerationData.MapGenState/DisableEnemyGeneration are peer-local and unserialized — mismatched FlatMap/enemy-generation settings across a paired saveload arm forked on which peer generated a camp
metadata:
  type: project
---

`MapGenerationData.MapGenState` / `DisableEnemyGeneration` are PEER-LOCAL and unserialized;
before `422653b01` `NewGameSettings.FlatMap` was not in the save either, so a flat world
reloaded as a normal world on whichever peer loaded it.

The player-persistence saveload arm's phase B ran the client `FlatMap:true` (generation off)
and the host loading the save (generation ON): un-parking the reclaimed player made it a
MapExplorer anchor, the host generated chunks around it, one rolled an enemy camp, the client
never could — a `camps` fork with the client stuck at the EMPTY fold `88201FB960FF6465` from
the first heartbeat of the epoch (sweep #10 at `715a679e5`, 2/2 OOB repro). It passed earlier
sweeps only because no camp chunk rolled where the wall-clock movement left the player:
host-only TERRAIN had been generated all along and no fingerprint surface folds terrain.

Now: the GameSettings block is v2 with `FlatMap`, `MapGenerationRegime` is the one helper
deriving the regime, and paired arms must configure BOTH roles with the same `FlatMap` and
`DisableEnemyGeneration`.

**How to apply:** tell for the future — camps at the empty fold on one peer only, with
movers/vision forking a few heartbeats later (the camp's spawners fielding ships) — means check
the two peers' map-gen regime match before chasing anything else.
