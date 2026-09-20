---
name: player-inventory-arrangement-diverges-by-design
description: "The playerInventories fingerprint field (slot ARRANGEMENT) diverges cross-peer as soon as the local player's inventory changes, because PlayerInventoryUpdateNotifier sorts only the local peer's OWN player; it is exempt by design and the verdict script only counts it — check playerInvTotals instead. It cannot reach a structure through an InventoryTransfer (containers folds every slot; the saturating leftover depends on a permutation-invariant fit sum), so a containers fork from a grab needs the acting player's TOTALS to differ. transfer.grab uses the panel dispatch API but defaults to Primary and omits SlotIndex; it cannot withdraw crafter output/Connector stock."
---

# The player-inventory arrangement diverges by design; chase totals, not slots (2026-09-12, 069 lane r12a)

**What you see.** `invdiff`/the verdict JSON report `playerInventoriesDifferenceCount` > 0 (hundreds or
thousands of samples) while `mismatchCount` is 0. On lane r12a the arrangement hash diverged from
(e1, hb 4503) — right after the client's own grabs — and stayed different until a recovery reload
re-aligned it; the next local inventory change diverged it again.

**Why (path-traced).** `PlayerInventoryUpdateNotifier.cs:117` calls `Inventory.Sort()` from the
presentation pump, and `PumpInventoryUpdates` (`:84-91`) drains and returns for any player that is not
`MePlayer` — so each peer sorts ONLY its own player's buffer. The transfer save carries the host's
copy (unsorted for a remote player), so a recovery reload re-aligns both. `Inventory.Sort()`
(`Inventory.cs`) reorders slots without merging stacks. The field is deliberately outside `Combined`
and the wire set (`DeterminismStateFingerprint.cs:83-95`), listed in the comparator's
`FINGERPRINT_EXEMPTIONS`, and `continuous_determinism_verdict.py:431-432` only counts it. The
order-insensitive sibling `playerInvTotals` MUST agree — a difference there is real.

**Why it cannot fork a structure.** The `containers` fold hashes tile + every `InventorySlot` in
order (`DeterminismStateFingerprintJobs.cs:517-552`), so both peers' structure copies are identical
up to the op. In `ApplyBufferTransfer` (`InventoryTransferNetworkOperation.cs:181-222`) the only
structure-affecting branch that reads the PLAYER copy is the saturating `leftover` returned to the
source, and that depends on `InventoryHelper.NumCanAdd` — a sum over slots of (empty → stack limit,
same item → remaining room) that is invariant under permutation. Slot-index puts are clamped on both
sides (`RemoveItemsFromSlot` = `min(quantity, slot quantity)`, host bake `sourceHas` from its slot or
its item total). Live proof: four lanes (plain grabs, grabs 3 s after a forced resync, 240 grab/put
ops in flight across a resync, 36 connectors placed in 2 s) — 18,226 shared samples, 0 differences
on `containers`/`beltItems`/`playerInvTotals`/`combined`. A `containers` fork from a pickup
therefore needs the acting player's TOTALS to differ across peers (an op dropped on one peer, a
non-op inventory write) — instrument that, not the arrangement.

**Verb facts (rechecked 074 t10, 2026-09-20).**
`ffauto:transfer.grab|<item|first>|<count>|<x>|<z>` calls the panel's
`InventoryOperationsDispatch.DispatchTransferFromStructure`, but omits BOTH the source-section
argument and `SlotIndex` (`LocalMultiplayerAutomationCommandRunner.ExecuteTransferGrab:4959-4965`).
The API defaults to `InventoryType.Primary` and rejects `count <= 0`
(`InventoryOperationsDispatch.cs:55-64`): supply a positive count; zero is a no-op, not a full stack.
`first` selects QuickTransfer; an item name selects PanelTransfer. A command receipt says the request
was submitted, not that items moved. Check authoritative inventory totals afterward.

This shortcut cannot withdraw a printer's Secondary output or Connector inventory. Real panel
stack clicks send the clicked section (`ModuleInventoryPanel.HandleStackClicked:111-125`). Use
that UI path and verify the transfer, or route output through a downstream Cargo Hold and grab
from its Primary inventory. The latter worked in t10 when a separate drag bug blocked output
clicks: twelve printed LDS transferred from the buffer and were used to craft the assembler.

Host-side rejects are logged `[InventoryTransferClientRequest] Reject at
transfer-bake/TargetFull` (holds full) — benign. Separate finding: `ActingPeerFeedback`
(`:148-175`) increments the `[Save]`d `ObjectivesTracker.ItemsCollectedFromBuilding` on the acting
peer only (`ObjectivesTrackingSystem.cs:191-196`) — objective progress, not a compared surface.
Related: [[verdict-script-rejects-eviction-records]], [[steam-desync-triage-from-the-client-side-only]].
