---
name: same-heartbeat-processing-order-desync-class
description: "Three 074 forks (T169, T172, T165) share one shape: a fixed-group system decides a same-heartbeat structural outcome (which grid survives a join/merge, which entity's ForceRecalc fires, which connector gets its marker) by walking a query in its own archetype-creation order — that peer's load history, not a canonical property — so a peer that loaded later reaches a different winner. Fix pattern (e08b384ca): sort the collected entities by tile/item/facing before processing. Tests: StationGridJoinOrderDeterminismTest, ConnectorChainJoinOrderDeterminismTest."
---

# Same-heartbeat processing-order desync class (074 T169/T172/T165, 2026-09-25)

**The shape.** A fixed-group system processes several same-heartbeat entities (new station
connections, a structural merge) by walking a query in ITS OWN ARCHETYPE-CREATION ORDER — which
is that peer's load history (join order, save/load order), not a canonical property of the
entities. Whenever the OUTCOME depends on which entity is processed first or last — "first/last
processed wins" logic: which entity's grid Add carries `ForceRecalc`, which station-grid object
survives a join, which connector gets its `RecalculateHaulersMarker` — a peer that loaded later
(a joiner, or a peer re-served during recovery) walks the same entity set in a different order and
reaches a different winner. All three instances below were caught by a `power`/`census`/`grids`
fork on the LOADED-LATER peer specifically, never on the peer that had been warm the whole time.

**The three instances (074, 2026-09-25).**
- **T169** (`StationConnectionsSystem`, fixed `e08b384ca`): walked `NeedsConnectionsUpdate`
  entities in query/archetype order; that order decided which entity's grid Add carried
  `ForceRecalc` and the order connections were appended, which in turn decided which station-grid
  object survived a join — host and M3 replaced the PRS grid, BEAST kept it, and each published
  different power numbers (ep3 hb 52096).
- **T172**: the same bug as a same-heartbeat grid MERGE (BEAST — the peer most recently re-served
  at the epoch-4 recovery for T169 — forked `power`+`census` at ep4 hb 65000).
- **T165**: the same order class on a connector chain — a connector processed after both its
  neighbours missed its `RecalculateHaulersMarker` (h5 host-odd-one-out one-heartbeat census
  forks).

**Fix pattern (`e08b384ca`).** Collect the entities first (e.g. `ToEntityListAsync`), then SORT
them by a canonical, save/load-independent key — tile, item, facing — before processing, so every
peer walks the identical order regardless of load history. This is a THIRD way a same-heartbeat
structural pass can fork, distinct from [[station-grid-mailboxes-must-share-one-holder]] (two
producers post to two different mailbox-holder entities) and
[[per-peer-gates-on-structural-changes-fork-the-census]] (the structural change is gated behind
something only one peer has) — here there is ONE producer and no per-peer gate, just no tiebreak
on the walk order itself.

**Audit recipe.** In any fixed-group system whose result depends on entity ORDER (not just
presence) — a merge, a "which one wins" decision, an append sequence — check whether the query or
job walks entities in raw query/archetype order with no explicit sort. `StationGridJoinOrderDeterminismTest`
and `ConnectorChainJoinOrderDeterminismTest` are the regression pattern to copy: build the SAME
same-heartbeat batch through two different load-history paths (a fresh world vs a re-served one)
and assert the winner agrees.

**Side effect:** renaming a Burst job method while fixing one of these can trip
[[burst-string-guard-baseline-follows-renames]] — check it in the same commit.
