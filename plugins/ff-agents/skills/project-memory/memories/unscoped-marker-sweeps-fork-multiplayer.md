# Unscoped marker sweeps and peer-local state in shared hashes fork multiplayer

**Date:** 2026-08-12 (fourth instance; class first seen 2026-07-05)
**Commits:** `8d23d83b1` (rotator), `94ba18f8f` (destroy sweeps + power hash), `d786d821f`
(placement system + asteroids/cbots hashes, WireVersion 16)

## The defect class

A kind-marker component (`BlueprintItemMarker`, `NetworkGhost`, …) tags WHAT an entity is, not
WHOSE it is. Any query or loop over "every entity with this marker" silently asserts "only one
owner's worth of these can exist." True in single-player, false in multiplayer: the local
player's preview, the `BlueprintMaster` remote-apply singleton, and injected placers coexist.
The sweep then acts on peer-local entities it does not own — a per-peer mutation, i.e. a
silent cross-peer fork.

**Signature:** cannot reproduce solo; nothing throws or logs; desync recovery does NOT cure it
(a state re-snapshot can't remove the cause, so the peer re-diverges every epoch — Ben's
2026-08-12 host log re-forked at heartbeat 8 of nine consecutive recovery epochs).

Four instances, one marker, four verbs: **placed** every marker at a remote anchor (bprace2,
2026-07-05) → **rotated** every marker (062 US1/F8) → **destroyed** every marker, so any
peer's placement deleted every other peer's held preview (2026-08-12) → **dragged + placed**
every marker at the local cursor (BlueprintPlacementSystem, 2026-08-12). Each was fixed in
isolation; the class-wide audit that followed instance 3 found instance 4 and two hash bugs
nobody had reported.

## The adjacent family: peer-local entities in shared hashes

A fingerprint/invariant query without ghost exclusions hashes entities that exist on one peer
only. The trap is **baked components**: a preview ghost is `Instantiate(prefab)` and inherits
every baked component, so "structure-only" components DO land on ghosts. `power` hashed held
transmitter previews via baked `PowerTransferEdge` (5 prefabs); `asteroids` hashed held
mining-station previews via baked `TerrainExtractorStation` (7 prefabs) — worse, the
terrain-item finder deliberately writes `TargetTerrainItem` on the held ghost each heartbeat.

## Rules

1. Before sweeping by a kind-marker, ask: **can more than one owner's instances coexist?** If
   yes, scope by an identity component (`BlueprintGhostOwner`). Scope by IDENTITY, never by
   timing — a before/after set-difference was defeated by the run's own ECB playback
   (`InstantiateAndPlaceBlueprintFromString`).
2. **Fail CLOSED**: require the owner component in the query/Execute signature. An un-stamped
   entity is skipped, never claimed. A skipped ghost is a presentation nit; a claimed one is a
   cross-peer mutation.
3. For any shared-hash or invariant query: **can this match something that exists on one peer
   only?** Standard exclusions: `DeletionMarker`, `BlueprintItemMarker`, `NetworkGhost`. Do
   NOT blanket-exclude `OutOfPlay` — under-construction structures wear it and ARE replicated.
4. **"Is the component baked?" decides ghost reachability** — grep the prefab GUIDs, don't
   trust intuition (two audit agents disagreed on exactly this; the prefab grep settled it,
   and the wrong answer was "safe").
5. When one instance of a defect class is found, **sweep for the whole class immediately** —
   and when replacing a query, diff the OLD query's exclusions against the new one (the first
   cut of the placement fix silently dropped a `WithNone<DeletionMarker>` and the review gate
   caught it).
6. Verification: RED→GREEN per fix, plus a **non-vacuity control** (the exclusion must not
   blind the surface: an `OutOfPlay` under-construction entity must still move the hash; the
   acting player's own ghost must still be processed — proves the system actually ran).
   Before trusting a RED run, confirm `last_domain_reload_after` is NEWER than the revert —
   a RED run raced the reload once and reported the fixed assembly's results.
