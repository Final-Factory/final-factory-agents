**TL;DR:** A client that loads the world (a join, a rejoin, a recovery) got the queued Trash Can ghost with a fleet-KNN marker the host's copy does not have, so `census` forked at heartbeat 8 of the new epoch. The load-shape repair that already strips that marker from construction sites now also covers queued ghosts.

## What forked

In the w3076 run-1 rejoin (a client's automatic reconnect after a 25.8 s host hang, ReclaimByGuid), the epoch-2 sample at hb 8 diverged on `census` only. Diffing the two halves' `CensusAtSample` lines (both 80 signatures, 138 entities; both `CensusDetail` lines are 81 and 81) leaves exactly one entity that differs:

- host `ED8DD168FE3B0D1D`: `Placeable, â€¦, OutOfPlay, PendingPlacement, ConstructionTaskRequester, CargoHold, â€¦`, no `KnnFleetEntity`
- client `773B8F12F6A2A252`: the same types **plus `KnnFleetEntity`**

That entity is the client's Trash Can, queued behind the marked Connector at (0,4) (w2849 `PendingPlacement`). It was neither the stopped construction bots nor the removal marks: those rows match on both sides.

## Why

The live placement strips `KnnFleetEntity` from every non-swap ghost (`BlueprintPlacementSystem.cs:1746`), and a queued placement is never a swap (`BlueprintPlacementSystem.cs:1864`). The load path re-instantiates the item prefab, which has it baked on, and only adds saved components. `ConstructionSiteKnnReconciliationSystem` (074 T108) repairs that on every loading peer, but its query was `OutOfPlay + ConstructionTaskData + KnnFleetEntity`, and a queued ghost has no `ConstructionTaskData` until `PendingPlacementSystem.Admit` gives it one.

## Fix

`ConstructionSiteKnnReconciliationSystem`: `[WithAll(OutOfPlay, KnnFleetEntity)] [WithAny(ConstructionTaskData, PendingPlacement)]`. It runs in `SaveGameManager`'s restoration sequence on every load: a plain join, a rejoin, a re-serve, a recovery apply and a host resuming a save all go through the same path. So the plain-join path had the same gap, and this closes it too.

Also:
- `Determinism-Fix-Patterns.md` pattern 11, "A prefab-baked component the live path stripped comes back on load".
- New pair scenario `MP-W3080-rejoin-with-queued-ghost`: MP-W3060's build-over-marked run in which the client reconnects (`net.dropreconnect`) while its Trash Can is still queued.

## Evidence

Kind: simulation

| Claim | Basis | Where |
|---|---|---|
| The only census difference after the rejoin is +KnnFleetEntity on the client's queued ghost | MEASURED: sig-set diff of the two halves' CensusAtSample (hb 8) and CensusDetail lines in the w3076 run-1 desync report | 1.0.0.37_desync_20261104_143440_2-8-3_host.txt, lines 88/1687 and 89/1688 |
| The new test fails without the fix and passes with it | MEASURED: `Reconciliation_StripsKnnFleetEntityFromALoadedQueuedGhost` RED on the old query ("Expected: False But was: True"), GREEN on the new one | slot2 editor, EditMode |
| A rejoin with a queued ghost no longer forks | PAIR_RESULT | pair run on this head (MP-W3080-rejoin-with-queued-ghost) |

Tests: FFEditorTests `ConstructionSiteKnnReconciliationSystemTest`, `CombatMoverProviderCatalogTest`, `LegacyKnnLoadPathWarmupTest`: 28 run, 28 passed, 0 failed
Determinism audit: PAIR_AUDIT
Save compatibility: none. No saved layout changes; the repair runs after load and removes a component the save never carried.

Request: w3080

ðŸ¤– Generated with [Claude Code](https://claude.com/claude-code)
