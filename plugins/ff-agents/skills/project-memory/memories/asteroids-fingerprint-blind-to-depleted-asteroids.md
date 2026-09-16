---
name: asteroids-fingerprint-blind-to-depleted-asteroids
description: "The `asteroids` determinism fingerprint hashes only asteroids currently TARGETED by a mining station or sourced by a miner (DeterminismStateFingerprintJobs.cs ComputeAsteroidsHash), so an exhausted asteroid drops out of the hashed set exactly while its deletion timing forks -- proven live: 16,776 shared heartbeats compared with 0 mismatches while the two peers disagreed for ~1,100 heartbeats on whether the asteroid existed. An entity-set change invisible to every surface is the shape to suspect when a real gameplay fork stays green; widen the instrument before theorising."
---

# The `asteroids` fingerprint is blind to depleted / untargeted asteroids (073, 2026-09-15)

`ComputeAsteroidsHash` (`Assets/Scripts/FFSystems/Multiplayer/DeterminismStateFingerprintJobs.cs`,
`AsteroidsJob`) builds its set from `TerrainExtractorStation.TargetTerrainItem` and miner
`LogisticsUnit.Source`, then folds `(CenterTile, OreRemaining)` per targeted asteroid. An asteroid at
`OreRemaining == 0` is no longer targeted, so it leaves the hash -- and that is the exact window in which
`AsteroidOutOfResourcesCheckerSystem` ramps and deletes it (the 073 frame-cadence fork,
[[fixed-group-engine-time-reads-are-frame-rate-desyncs]]). Asteroids carry no KNN/vision/C3/static-index
markers either, so `vision`/`movers`/`combat` do not fold them.

**Proven live, not argued.** Built-player leg f4 (shipped 0.50.0.19, Rosetta Mac host at 20 fps vs
BEAST Windows client at 240 fps): host deleted the asteroid by hb 14015, client by hb 15146; the typed
checkpoint over that window (`f4-cp1`, 16,776 shared heartbeats, hb 1..16776) reported 0 mismatches and
`NO DIVERGENCE`. Fourteen earlier paired legs on the same world were green for the same reason.

**Rules this adds.**
- A green fingerprint over a window in which you KNOW an entity-set change happened on one peer is a
  blind-spot finding, not a pass. Instrument the entity set directly (a per-peer existence/snapshot poll,
  e.g. `snapshot/nearby` -- see [[built-pair-lab-traps-073]] for its radius trap) before believing the hash.
- Widen the instrument at the surface that OWNS the entity kind. DONE the same day (Ben: "Both"):
  `asteroids` now also folds every `Asteroid` with `OreRemaining == 0` (no DeletionMarker / preview
  ghost), on BOTH the serial and the batched job call sites (`CreateExhaustedAsteroidQuery`,
  `AsteroidsFingerprintExhaustedTest`). Not a crown-jewel path, no new surface so no three-mirror update
  ([[wire-surface-adds-have-three-mirrors]]); the pinned golden did not move because its fixture has no
  zero-ore asteroid. Follow-up 073 T021: a general entity-set / archetype-census surface (new field →
  three mirrors + peer-local exclusions).
- A widened instrument is proven when it goes POSITIVE. **Proven live 2026-09-16 (073 leg h1):** a
  built Mac↔Windows pair at scratch `ca67a7c9d` (= `a7ac582d8` with `800974582` reverted, see
  [[revert-pair-proves-a-widened-instrument]]) ran the f4 shape; `fpcompare.py` epoch 1 = 1,201 shared
  heartbeats, 4 mismatching (hb 1198–1201), fields `asteroids` + `combined` ONLY; the host's
  `RuntimeDesyncDetectorSystem` said `diverged … at heartbeat 1200 (surfaces: asteroids)`, recovered the
  client, and epoch 2 was clean over 5,231 heartbeats. The depleted husk cannot mask it: its prefab bakes
  `DepletedAsteroid`/`AsteroItem`/`CosmicTerrain` and NO `Asteroid`, so the deleting peer's exhausted set
  goes empty while the other peer still folds `(tile, 0)`.
- The first-diverging surface a live desync reports (Hazel: `grids+power`, `movers+vision`,
  `camps+movers`) can be many heartbeats downstream of an entity-set fork no surface sees; archetype
  creation order ([[ecs-iteration-order-is-archetype-creation-order]]) is the carrier.
