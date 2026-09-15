---
name: fixed-group-engine-time-reads-are-frame-rate-desyncs
description: "Inside a fixed (heartbeat) group SystemAPI.Time.DeltaTime / ElapsedTime is the ENGINE frame delta the controller group pushed, not the heartbeat step -- any simulation-visible accumulator built on it forks peers by frame rate (073: a 20 fps peer deleted an exhausted asteroid ~1150 heartbeats before a 240 fps peer, proven on built Mac<->Windows players). Read FFTimeData.deltaTime. A reader that only writes presentation (LogisticsBay animation children) is the same smell but not a desync -- adjudicate by tracing what the write feeds."
---

# Fixed-group `SystemAPI.Time.*` reads are frame-rate desyncs (073, 2026-09-15)

**The mechanism.** `FinalFactoryControllerSystemGroup` pushes the engine frame delta (capped at one
heartbeat step) into World time every frame (`FinalFactoryControllerSystemGroup.cs:64`); the fixed-step
group does NOT push its own time -- it only sets `FFTimeData.deltaTime`
(`FinalFactoryFixedStepSystemGroup.cs:53-70`). So a system in `FFFixedPreTransformGroup` (or any fixed
group) that reads `SystemAPI.Time.DeltaTime` gets `1/fps`, and `ElapsedTime` gets wall-clock since world
start. At 16 UPS a 20 fps peer sees dt=0.05 per heartbeat, a 240 fps peer dt≈0.004: a 12x ramp difference.

**The bug that proved it.** `AsteroidOutOfResourcesCheckerSystem` ramped a depleted asteroid's emissive
value by `Dt * 250000` per heartbeat and deleted the asteroid (+ spawned its husk) past 1,000,000.
Fixed at `800974582` (read `SystemAPI.GetSingleton<FFTimeData>().deltaTime`); guard
`Assets/Tests/Mining/AsteroidDepletionCadenceTest.cs` (81 vs 960 heartbeats before, equal after).
Live proof on the SHIPPED 0.50.0.19 built players (Rosetta Mac host throttled to 20 fps, BEAST Windows
client ~240 fps): host deleted ≤49 hb after zero ore, client ~1150 hb (~70 s) later; rebuilt at
`fab5a1714` both deleted within one 3 s poll of each other. Evidence: `specs/073-hazel-playtest-mp-fixes/plan.md`
(22:30 UTC header), lab `/private/tmp/ff073-hazel-20260915/xplat/` on M5.

**How to tell a real desync from a smell.** The read is only a fork if what it feeds is
simulation-visible. `LogisticsBayAnimatorSystem.cs:23` reads `ElapsedTime` in the same fixed group and
writes `LocalTransform.Position` (0 vs y=9999) on the bay's `AnimationEntity` children -- those carry
only dynamic transforms + render components (baker `AnimationAuthoring.cs:25-40`), match no KNN query
(`KnnSystem.cs:391-401` requires a vision marker), hold no `Placeable`/grid claim, and no fingerprint
folds them (`PresentationRotatorSystem.cs:34-38` documents the same for rotator children). Peers animate
out of phase; nothing forks. Trace the WRITE's consumers before calling it a bug.

**Hunting the class.** `grep -rn "SystemAPI.Time\.\(DeltaTime\|ElapsedTime\)" Assets/Scripts/FFSystems`
and keep every hit whose system is in a fixed group; for each, name the component it writes and who reads
it. Related: [[fixed-group-reads-of-localtoworld-are-frame-count-bugs]] (the transform-cadence sibling),
[[asteroids-fingerprint-blind-to-depleted-asteroids]] (why the audit missed this one).
