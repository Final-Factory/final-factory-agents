---
name: census-fingerprint-surface-design
description: "The `census` determinism surface (073 T021, wire v20, index 21) counts entities per archetype signature built from GAME component types only (namespace starts with FF, minus FFComponents.Presentation/Selection and an explicit peer-local list -- now also `AttackWarningData`); every engine type is stripped, `Disabled` folds only beside a game type, Prefab/DeletionMarker/NetworkGhost/BlueprintItemMarker entities are dropped. It catches ANY cross-peer entity-set fork on the heartbeat it happens: the comet wall-clock spawner, the cosmic-object revealer skew, and -- after a desync RECOVERY -- 8 orphan logistics route-display sets the reset never destroyed (NOT the comet, which carries `LimitedLifetime` and is reset-destroyed anyway). Diagnose a census red with the `CensusDetail` dump and a per-heartbeat row diff, never by guessing; keep diagnostic byte limits under 2^31."
---

# The `census` fingerprint surface (073 T021, 2026-09-16)

**Why it exists.** Per-kind surfaces only see the kinds they fold; an entity one peer deleted (the 073
depleted asteroid) stayed green for 16,776 heartbeats. `census` = Fold over ascending
`(signature, entityCount)` where signature = Fold over the ascending `StableTypeHash` of an archetype's
KEPT types (`DeterminismStateFingerprintJobs.cs`, `CensusTypePolicy`/`CollectCensusRecords`; signatures
MERGE across archetypes). Appended at wire index 21, `WireVersion 20`, three mirrors
([[wire-surface-adds-have-three-mirrors]]) plus `CensusDetail` in `NetworkDeterminismAuditSurface`.

**The policy that survived a Mac<->Windows pair (v2, v3).** v1 ("strip a few namespaces") mismatched on EVERY
heartbeat: `Unity.Entities.Graphics.RenderFilterSettings` is not in `Unity.Rendering`, particle companion
entities, `AddEntityNameDebugMarker` on the client's loaded entities only, `MePlayer` vs `HostPlayer`,
the client-only `HostObjectivesTrackerProjection`, display arrows, warning pins, VFX children,
`UpdateMarker`, three load-settling markers. v2: KEEP only types whose namespace starts with `FF`, minus
`FFComponents.Presentation`/`FFComponents.Selection` and an explicit peer-local list; strip every engine
type; fold `Unity.Entities.Disabled` only when a game type survives; no game type => the entity is
peer-local machinery and is dropped. v3 (T025) added `AttackWarningData` (the unserialized HUD warning; a
joined peer never carries the ones the host raised before the join). Convention: a presentation/UI
component lives in those two namespaces or goes on the explicit list. `StableTypeHash` IS
cross-platform stable (0 same-list rows with different hashes). NOTE `LimitedLifetime` and `ScaleOverTime`
are on the strip list, so a `[LinearMotion, Comet]` row IS a spawned comet (it carries a 60 s lifetime).

**How to diagnose a census red.** Run the pair with `AuditCaptureProfile: diagnostic`,
`AuditDiagnosticSurfaces: ["CensusDetail"]`, a heartbeat window, and limits that FIT IN INT32 (2^30 /
2^31 fail as "Diagnostic event and byte limits must all be positive" and the player sits in the error
phase). Rows are `sig=<hex> n=<count> types=[a,b,c]` per heartbeat; diff the two peers' rows per shared
heartbeat and name the differing type lists (lab: `xplat/censusdiff.py`, `censusfirst.py`). The window
anchors to ONE epoch — the first block after arming, closed by the next epoch
(`NetworkDeterminismAudit.cs:227-262`, 045 T031b) — so a POST-RECOVERY epoch is never captured; for that
use the single-player reset probe ([[single-player-reset-probe-for-recovery-leftovers]]).

**What it found (all live, Mac host <-> Windows client).** A `[LinearMotion, Comet]` entity on one peer
only ([[elapsedgametime-is-the-per-peer-wall-clock]], fixed T022); `FogObserver` added to an asteroid 3 hb
earlier on the host (`CosmicObjectRevealerSystem`, fixed T023); and after a desync RECOVERY the census
stayed red for the whole epoch. **The recovery cause was mis-attributed at first** (to `Comet` missing from
`FinalFactoryGrid.ResetGameEntitiesAndObjects`): the comet has `LimitedLifetime`, which that reset already
destroys, and expires in 60 s — it cannot hold an epoch red for 3,128 hb. The real leftover, found by the
reset probe: a freshly loaded world holds 8 orphan logistics route-display sets (`ArrowDisplayMetaData`
records with `Parent = Entity.Null`, `Ready = false`, no `UpdateMarker`, 3 arrow entities each = a
24-entity `[ArrowAngleMaterialProperty, BaseColorMaterialProperty, ArrowOffsetMaterialProperty]` row);
both orphan guards only revisit records WITH `UpdateMarker`, so a recovery reload on top of a live world
kept 24 and loaded 24 more (48 vs the host's 24, every heartbeat). Fixed T024:
`DestroyEntities<ArrowDisplayMetaData>()` in the reset. A recovery is the normal load path
(`GameStateRpcManager.cs:1128` -> `LoadGameFromMultiplayerRequest` -> `LoadGame` -> `ResetGame`), so
any entity a running world holds that the reset does not list is a recovery leftover. Also seen: a
deferred `census` verdict at hb 8 of every post-recovery epoch (pre-apply samples), no second recovery.

**Reading a census verdict.** `surfaces: census` alone with every per-kind surface green = an entity-set
fork no other surface folds — get the dump. `asteroids+census` at the same heartbeat = the per-kind
surface and the census agree (h3: the deletion fork at epoch 2 hb 2264). Red on EVERY heartbeat from the
first sample of an epoch = a set-size difference that pre-dates the epoch (a leftover or a load-path
asymmetry), not a fork that happened inside it.
