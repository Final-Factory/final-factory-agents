---
description: A player's inventory is compared on one peer only, so lockstep code that branches on whether items FIT it forks when it is full. The construction-bot hand-over did (w170); the host now bakes it as an op. Prove such a fork with ffauto:inventory.remove.
---

# Lockstep code must not branch on whether items fit a player's inventory (w170, 2026-10-01)

**The fork.** Live 0.50.0.61, a mass deconstruction in a 4-player game: `cbots`+`census`, both clients
agreeing against the host. One player-owned construction bot was idle and re-assigned on the host and
still `AtOwner` on the clients. No op in the fork window.

**Why.** A bot emptied its hold into its owner's `InventorySlot` buffer with a plain `TransferAll`
(`ConstructionBotTaskSystem.HandleBotAtOwner`, `ReturnBotInventoryToSource`) and went idle only when the
hold was empty. Player inventories are outside `Combined` (`FingerprintResult.PlayerInventoryHash`), so
two peers may hold different copies. A full inventory turns that difference into simulation state: the
transfer lands on one peer only. Slot ARRANGEMENT alone does not change fit (see
[[player-inventory-arrangement-diverges-by-design]]); the copies' item totals or free slots have to
differ. What made them differ live was never found.

**The fix shape (#890).** The bot waits with its cargo. The host bakes what fits on its copy against a
throwaway clone of the owner's buffers and authors `ConstructionBotHandOver` (outbound only, the
`LootSpawn` shape, published from a `SystemBase` in `FFControllerLateGroup`). Every peer removes the baked
amount from the hold, clamped, and saturating-adds to its copy; nothing returns to the hold. One batch in
flight at a time, or two bots get promised the same free slot.

**Still lockstep readers of a player's copy:** `TakeItemFromInventory` and the assigner's `HasItem`
(item totals, not fit).

**How to prove this class.** Fill the inventory (`inventory.add|Iron Ore|999999`), make bots wait with
cargo (`construction.cut`), then `ffauto:inventory.remove|Iron Ore` on ONE peer: a local-only write that
changes only that copy. Before the fix: a `cbots` verdict four heartbeats later. After: compare with
`REPORT_ONLY_FIELDS=playerInvTotals` (the injected field) and every other field must match. Since #883
`ConstructionDetail` shows `cargo=` per bot and `inv[p:guid]:slots,free,items,h` per owner, so the two
halves of a desync report show the difference directly.

**Reading a report with no detail for the cause.** When all hashed fields matched until the fork and no op
landed in the window, list what the diverging entity reads that is NOT hashed. Here: bot cargo and the
player's inventory. `dist=` in `ConstructionDetail` is context, not hashed.
