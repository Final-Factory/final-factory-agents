---
name: station-grid-mailboxes-must-share-one-holder
description: "Every producer of a StationGridUpdateCommand must post to the SAME mailbox entity on every peer. PlaceableDeletionSystem posted its Removes to MePlayer while StationConnectionsSystem posted Adds to HostPlayer, and StationGridMembershipSystem drains each mailbox entity separately in chunk order: one entity on the host, two on every client, so a Remove+Add pair (a SwapItem upgrade beside a Station Core) resolved to different grid topologies — haulers red for one heartbeat, then grids+power+census forever, and every recovery re-forked at hb 8 (grids are derived on load). Found by ruling the suspected tag OUT with an idle no-chain leg; fixed cba0dc6fd (073 T031)."
---

# Station-grid mailboxes must share one holder (073 T031, 2026-09-18)

**The shape.** `StationGridUpdateCommand` is a MAILBOX buffer on player entities (`StationGridUpdateCommandAuthoring`,
TODO-#247 "decouple the player from grid updates"). `StationGridMembershipSystem` (`FFFixedInitializationGroup`)
runs an `IJobEntity` over EVERY entity carrying the buffer, drains each one separately (`updater.Clear()` per
mailbox) in chunk order. So two producers posting to two different holders are ordered per peer:
- `StationConnectionsSystem.cs:21` → `GetSingletonEntity<HostPlayer>()` (Adds, on `NeedsConnectionsUpdate`).
- `PlaceableDeletionSystem.cs:71` → `GetSingletonEntity<MePlayer>()` (Removes, on `DeletionMarker`) — BEFORE the fix.
- `RecalculatePositionsOnGridSystem.cs:41` → `Player[0]` by query order (load-time only; harmless while it is
  the only mailbox with commands at that moment, but the same smell).

On the host MePlayer == HostPlayer: one buffer, append order. On a client they are two entities, drained in
whatever order their chunks come — and a SwapItem upgrade (construction bots replacing a Solar Panel frame
next to the Station Core at hazel1831 tiles (5,-22)/(7,-22)) posts a Remove for the old frame and an Add for
the new one in the same heartbeat. The client built an extra `StationGrid` at (5,0,-22) and the core's
`StationGridReference` dangled (`HaulersDetail` `moving=?`); grids+power+census stayed red, and each recovery
re-forked at hb 8 because grid membership is rebuilt from the mailbox on load.

**Fix.** One agreed holder: `PlaceableDeletionSystem` requires and posts to `HostPlayer`
(`StationGridRemoveCommandMailboxTest`: a client-shaped world where MePlayer ≠ HostPlayer, RED host mailbox 0 →
GREEN). Paired: leg g11 on `cba0dc6fd` ran 4,476 shared hb through the walk, a 10-ship transfer and a
platform deconstruction with grids/power/haulers/fleets green. Any NEW producer of grid commands goes to the
HostPlayer mailbox until #247 replaces it with a singleton.

**How it was found — the idle control leg.** The fork always landed ~hb 684–691 on the hazel1831 legs and was
first blamed on the T029 tag (a calc step at 687). Two cheap legs settled it before any theory: an IDLE leg
(join, no chain) ran 7,827 hb clean → the fork tracks the chain, not the join; a WALK-ONLY chain
(`wait|2; movement.goto|160|40|40|150`) forked at chain start + 203–206 hb in every run → the host player's
approach alone triggers it (the player's bots start swapping panels). Then `HaulersDetail` + `CensusDetail` +
`PowerSatisfactionDetail` on one diagnostic leg named the entity, and `snapshot/nearby?x=7&z=-22&r=12` (TILE
coordinates) named the structures. Rule: when a fork sits at a fixed offset from BOTH the join and the chain,
run the no-action control first — it is one 7-minute leg and removes a whole class of hypotheses.
