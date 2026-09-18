---
name: per-peer-gates-on-structural-changes-fork-the-census
description: "Three census forks found in one 073 session share one shape: a fixed-group system makes a STRUCTURAL change (instantiate, add/remove a tag, link into a LinkedEntityGroup) behind a per-peer gate — the local camera (`InserterMovementSystem` route displays, T027), the player's presentation `LocalTransform` plus one unsaved shared position (`BreadcrumbSystem`, 26,464 crumbs in hazel1831, T028), or `MePlayer` (`PlayerEntityProximitySystem` tagging Defense Platforms and their ships `ValidForPlayerAbility`, T029 — resolved by keeping the tag local, stripping it from the census and moving the one simulation reader onto a per-player record). Audit recipe and the tell for an unsaved per-peer tag (census red on EVERY heartbeat after a recovery) inside."
---

# Per-peer gates on structural changes fork the census (073 T027/T028/T029, 2026-09-17)

**The shape.** A system in a fixed group instantiates an entity, adds or removes a component, or edits a
`LinkedEntityGroup` — and the decision depends on something only THIS peer has: its camera, its own
`MePlayer`, a player's presentation `LocalTransform` (predicted locally, interpolated remotely), or
unsaved system state. The entity set then differs across peers and the `census` surface
([[census-fingerprint-surface-design]]) goes red on the heartbeat it happens.

**The three instances.**
- **T027 — camera-gated link (fixed `8d28aa8e8`).** `InserterMovementSystem.GetRouteDisplay` instantiates a
  route display for every inserter on every peer, but the block that added `UpdateMarker` and set
  `Parent`/`Ready` ran only inside `GridHelper.IsWithinCamera`. Only a marked display is linked into its
  inserter's `LinkedEntityGroup` (`LogisticsDisplayLinkedEntitySetupSystem`), and a structure dies by a plain
  `DestroyEntity`, so removing an inserter a peer never looked at left its display (3 arrow entities the
  census counts) on that peer only. Fix: the FIRST configuration (`!Ready`) is not camera-gated. The 8
  "orphan" display sets a fresh `hazel1831` load holds were NOT orphans: each was referenced by an Inserter
  Bot's `LogisticsRouteDisplayItem` buffer. **Check owner-side references before calling a record a leak.**
- **T028 — breadcrumbs (fixed `655d30d9f`).** `BreadcrumbSystem` read each player's `LocalTransform` against
  ONE unsaved "last crumb" position shared by all players: two players more than 300 units apart each
  dropped a crumb EVERY heartbeat (26,464 crumbs against `MaxBreadcrumbs: 40`; the fader removed one per
  heartbeat, first-of-the-oldest in query order), and the count forked when a moving player crossed 300
  units from another (built pair, hb 667: client +1/+2/+3). A crumb carries a `[Save]`d `FogObserver`, so
  it is simulation state. Fix: stateless — one live trail crumb per 300-unit cell of
  `Player.SimulationPosition`, players in `Guid` order; the cap ranks by age then position and applies in
  one heartbeat. Side effect: headless host 139 → 244 fps on that save.
- **T029 — `ValidForPlayerAbility` (fixed `4b775f06c`, Ben's option B).** `PlayerEntityProximitySystem`
  queried `MePlayer` only and tagged Defense Platforms within 150 units of THAT peer's player, and their
  owned ships. The tag fed `AbilitySystemHelper.InactiveAbilityShape`, which the host's ordered-ability
  validator (`PlayerAbilityFireCandidates`) shared with the per-peer ability systems, so the host judged a
  client's cast by the HOST player's proximity. Fix shape when a per-peer tag has ONE simulation reader:
  keep the tag local (it still drives the HUD and the local preview), STRIP it from the census
  (`CensusTypePolicy.BuildExplicitStrip`), and give the reader an agreed per-player record — the system
  now runs over every `Player` and writes each player's `NearbyEntity` buffer from its replicated
  `SimulationPosition`; the validator keeps a ship if it is a `PlayerShip` or its `FleetShip.OwnerEntity`
  is in the CASTER's buffer. Live: the platform/Bat rows that differed on g9d were equal on g10 at the same
  heartbeats. The strip's residual (a per-peer archetype split perturbing order-sensitive ship consumers)
  did not show on g10/g11 — the fork that DID show was [[station-grid-mailboxes-must-share-one-holder]].

**Audit recipe.** Grep fixed-group systems for `WithAll<MePlayer>`, `GetSingletonEntity<MePlayer>`,
`IsWithinCamera`, `CameraState`, and `LocalTransform` reads on `Player` entities; keep only the hits that
instantiate, add/remove components, or edit a `LinkedEntityGroup`. Seen and not chased:
`PlaceableDeletionSystem.cs:71` (grid-update commands appended to `MePlayer`),
`PlayerFleetHealingSystem.cs:36` (gated on `MePlayer`).

**The tell for an UNSAVED per-peer tag.** After a desync recovery the census is red on EVERY heartbeat of
the new epoch: the client reloaded the host's snapshot (no tag), the host was never reloaded and keeps its
own. A recovery loop with `census` first in every verdict is this, not a broken recovery.
