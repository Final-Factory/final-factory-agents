---
name: every-new-system-runs-in-a-test
description: "A new ISystem (a presentation or animation system included) is scheduled at least once by a test, in an EditMode world, with an entity it matches. A system nobody runs in a test fails on the first frame in a real world, and a guard that skips a method by name misses a Burst error a player build finds."
date: 2026-10-09
---

# Every new system runs in a test

**Rule.** For each new or changed `ISystem`/`SystemBase`: a test creates the world, makes an entity the system
matches, and calls the system's update at least once (`World.CreateFFISystemForTesting<T>()`,
`UpdateAndComplete`), then asserts what it wrote. A system tested only through its logic helpers is untested.
Presentation systems count: they run on the first frame of every world.

**Why (w809, 2026-10-09).** `RailgunAnimationSystem`'s job took the structure's pose as an `in LocalTransform`
parameter and wrote its parts' poses through a writeable `ComponentLookup<LocalTransform>`: Unity's job safety throws
an aliasing error the first frame a gun exists. Forty-odd railgun tests and the full fast suite (9,381 tests) were green
because none scheduled that system; loading a new golden fixture in PlayMode threw it. The same request's first
player build failed Burst (BC1016) on `RailgunSystem.OnCreate`, which carried its own `[BurstCompile]` and built a
`FixedString64Bytes` from a string, because `BurstManagedStringGuardTest` skipped lifecycle methods by name (fixed: it
now scans an `OnCreate` that has its own attribute).

**How to apply.** Write the system's test before the first in-game run. Make it red first on the broken shape (restore
the old code, run, see the exception, restore the fix): w809's two animation tests failed with the aliasing error on the
old job and pass on the new. A first built player or PlayMode load of a new feature is the second check, not the first.
