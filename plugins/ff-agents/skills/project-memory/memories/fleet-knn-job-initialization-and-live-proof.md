---
name: fleet-knn-job-initialization-and-live-proof
description: Initialize every reused job input; a default zero chunk size caused a Bat transfer census fork across ARM and x64, fixed and proven on all three physical machines.
---

# Reused jobs need complete inputs

Feature074 T123: `FriendlyKnnDisablerSystem.OnUpdate` reused both
`EnemyKnnDisablerSystem.KnnDisablerJob` and `KnnEnablerJob` without setting `ChunkSize`.
The shared jobs call `GridHelper.AreChunksInRadiusActive`, whose float-position chunk
conversion divides by chunk size (`GridHelper.GetChunkFromPos(float3,int)` and `SnapToGrid`).
The omitted field was zero. Nonfinite conversion is a cross-platform hazard; the exact CPU
conversion result was not instrumented in this investigation.

T36 reproduced a census fork two heartbeats after the host transferred one Bat to a defense
platform. Host and Windows had 13 idle Bats with `DisableKnnMarker`; native M3 had 12 plus
one otherwise-identical Bat without that marker. The parent set `ConfigConstants.ChunkSize`
on both job schedules. `FriendlyKnnDisablerChunkSizeTest` exercises the real system and ECB
at positive and negative chunks: two near-active cases failed before the fix; all four cases
passed after it. The synchronous-Burst fast suite passed 4350 tests, with 16 existing skips.

The repaired revision `f8c04468b` then replayed the same save on M5 Rosetta, M3 native ARM and
BEAST Windows. T37b matched all 26 fields through 6161 shared heartbeats, including transfers
from all three peers. Host and M3 matched all 6000 detailed census rows. This diagnostic
replay closes the repair; it is not a substitute for a strict gameplay acceptance leg.

When reusing a job, inspect every input field at every initializer. A default numeric value
can compile, pass unrelated tests and fail only on different hardware. Keep component census
strict, reproduce the structural difference, use a focused RED→GREEN test, then replay the
reported action on the physical fleet.
