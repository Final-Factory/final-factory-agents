---
name: order-sensitive-vision-buffer-consumers-open
description: OPEN hazard — TargetingSystem, KnnProjectileCollisionSystem, and DefensePlatformDefenseSystem consume a KnnVision buffer in raw build order with no tiebreak, a live cross-peer divergence risk on co-located sources
metadata:
  type: project
---

Flagged OPEN in the 055 R36 commit (`8dfeb1d1e`, "FLAGGED, NOT FIXED") and still unaddressed as of
game-repo tip `7304103d6`: several combat systems consume a `KnnVision` buffer in raw
archetype/build order instead of by a canonical key, making them peer-divergent whenever
co-located sources tie for nearest.

Confirmed still present at these locations:

- `TargetingSystem.GetValidTargets`/`SelectBestTarget`
  (`Assets/Scripts/FFSystems/Combat/TargetingSystem.cs:165`, `:199`) — `SelectBestTarget` takes the
  first qualifying entry in buffer order, no score or key tiebreak.
- `KnnProjectileCollisionSystem`
  (`Assets/Scripts/FFSystems/Combat/Projectiles/KnnProjectileCollisionSystem.cs:120`, `:126`) —
  takes `Vision[0]` for an enemy hit and `Vision[^1]` for a fleet hit.
- `DefensePlatformDefenseSystem`
  (`Assets/Scripts/FFSystems/Combat/DefensePlatformDefenseSystem.cs:155`) — takes `Vision[0]` as the
  attack position and propagates it to other platforms as a `DefensePlatformAttackOverride`.

Nearest-first ties on exactly co-located sources — the same class of pose collision R34b/R35/R36/R37
fixed for the KD-tree BUILD itself (see [[055-liveness-and-comparison-surface-lessons]] and
[[fixed-group-reads-of-localtoworld-are-frame-count-bugs]]) — can still flip which entity these
three land on, cross-peer, even with a fully canonical tree.

**The protected pattern to copy when someone picks this up**:
`UnitOverlapPreventionSystem` (`Assets/Scripts/FFSystems/Core/UnitOverlapPreventionSystem.cs`)
consumes via `KnnSourceOrder.Rank64`, not buffer position — it is the one consumer in this family
already immune to this class.

**This is a driver+Ben design item, not a mechanical fix** — do not silently "fix" it as a drive-by
on unrelated work. It needs a decision on whether all three should re-sort by the `KnnSourceOrder`
key or take a different tiebreak, and what the blast radius of changing target/attack selection is
for existing balance.
