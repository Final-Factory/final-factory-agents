---
name: a-does-not-resolve-log-from-saved-history-is-not-a-fork
description: "The g15 'Commanded ship object id 720 … does not resolve on this peer' line was a stale saved row, not a crew fork: the two [Save]d per-player ability buffers (PlayerAbilityFireIntent / PlayerAbilityCommandedShip) were never pruned (52 consumed intents + 92 rows on the hazel1831 host, 996 on its partner), rows carry no kind, and per-kind sequence lanes made a new cast walk another kind's old rows. Fixed 073 T035 (27df24bed): unique-per-actor sequences + prune at apply. The diagnostic recipe: load the SAME save solo in the editor, dump the buffers, and find the id in the world census before believing a per-peer explanation."
metadata:
  type: project
---

# A "does not resolve" log from saved history is not a fork (073 T035, 2026-09-19)

**What it looked like.** Both peers of paired leg g15 logged the identical
`[PlayerAbilityFire] Commanded ship object id 720 (kind ObliteratorDisc, sequence 1) does not resolve
on this peer.` after the host spawned 4 Krillos and cast the Obliterator disc. The handoff read it as a
deterministic 3-of-4 crew and listed spawn-side candidates (a ship `Disabled` between validate and apply,
a `PendingCombatIdentity` re-stamp, a duplicate id losing `TryAdd`). None of those was it.

**What it was.** `hazel1831` loaded SOLO in the editor showed: the host player's `[Save]`d
`PlayerAbilityFireIntent` buffer held 52 consumed intents (Frenzy 1..22, Plasma 1..29) and its
`PlayerAbilityCommandedShip` buffer 92 rows — Hazel's entire Frenzy history — and the co-op partner's
player 996 intents. Nothing had ever removed a row. Object id 720 was a Bat in Frenzy rows 1/3/5/7 that no
longer existed (716–719 and 721–724 are live bots/Bats; `NextObjectId` was 11953, so no new Krillo could
be 720). Rows carry no kind and are joined to their intent by `EventSequence` alone; the host baked the
Obliterator's LANE sequence (`LastAppliedEventSequence + 1` = 1), so cast 1 walked the stale Frenzy
sequence-1 rows {719, 720, 721, 723}: three resolved to Bats and were silently skipped by the
applier's unit-kind check, 720 was absent and logged. Cast 2 (sequence 2) walked {724, 726, 748, 749},
all still alive — hence no line, and the handoff's "cast 2 unobserved" gap. The four Krillos all
resolved; the disc spawned with `crew=4` on both peers.

**Fix (27df24bed).** `PlayerAbilityFireSequencing.NextEventSequence`: the host bakes
`1 + max(every lane's LastAppliedEventSequence, every pending intent's sequence)` — unique per actor
across kinds, with the per-lane exactly-once guard untouched. `CombatAbilityCommandApplySystem.
PruneConsumedIntents`: at the top of every update, per actor, on every peer — consumed intents removed
in place, then rows whose sequence no remaining intent holds (clears pre-existing history on load). No
save-layout change (`SerializationUtil` copies structs by raw layout, so adding a `Kind` to the row would
have needed an UpgradeStep). Residual: two kinds validated in ONE drain still share a value; the kind
check keeps that deterministic.

**How to apply.**
1. **A deterministic error on BOTH peers is evidence about shared STATE, not about a peer.** Before
   listing per-peer mechanisms, load the same save solo in the editor and look the id up in the
   world census (`WithAll<DeterministicCombatObjectId>` + `IncludeDisabledEntities | IncludePrefab`).
   A missing id with live neighbours on both sides is a dead object referenced from saved state.
2. **Dump the `[Save]`d buffers the op reads, not just the components the op writes.** The rows the
   applier walked were visible in one `execute_code` probe; the g15 report profile carried none of it.
3. **Anything `[Save]`d that only ever grows is a bug even when it is deterministic.** Ask "who removes
   from this buffer?" — `grep RemoveAt|RemoveRange|Clear` over the readers. Here the answer was nobody,
   and the cost was save bloat, O(n) scans per heartbeat, and a false fork report.
4. **A row keyed by a per-lane counter in a buffer shared across lanes WILL collide.** Either key the
   row by (lane, sequence) or make the counter unique across lanes at the point of issue.
5. The positive Obliterator instrument is on record (Wittlebase, editor): intent consumed at the apply
   heartbeat, disc spawned `crew=4` 9999 above the cast point, dropped to the cast plane ~30 hb later,
   Krillos ringed at r≈30, launch = `ScaleOverTime.Finished` + `MultiUnitCastAbilityTracker.Finished` +
   `LimitedLifetime`, markers released, then the fleet-hide tag returned. An `EditorApplication.update`
   recorder (`+=`, self-removing after N seconds, appending one line per heartbeat to a scratch file) is
   the cheap way to watch a 3-second effect from a bridge whose round trip is ~1–5 s.
