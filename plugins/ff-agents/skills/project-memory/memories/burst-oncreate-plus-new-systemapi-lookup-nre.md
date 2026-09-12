---
name: burst-oncreate-plus-new-systemapi-lookup-nre
description: "Adding a SystemAPI.GetComponentLookup to an ISystem whose OnCreate is [BurstCompile] made the Burst-compiled OnUpdate throw NullReferenceException in the EditMode test world (managed path passed; the unmodified system passed; JIT-cache wipe and the EnableBurstCompilation toggle did NOT clear it). Removing [BurstCompile] from OnCreate fixed it. Discriminate a Burst-only failure by one Burst-off test run and a git-stash of the change."
---

# Burst OnCreate + a new SystemAPI lookup = NRE in the Burst-compiled OnUpdate (2026-09-12, 069)

**Symptom.** New EditMode tests for `OldBeamShootingSystem` all failed with
`System.NullReferenceException … thrown from a function compiled with Burst` at frame
`OldBeamShootingSystem.OnUpdate`, after the fix added `Players = SystemAPI.GetComponentLookup<Player>(true)`
and a `[ReadOnly] ComponentLookup<Player>` job field. No Burst compile error anywhere.

**Discrimination that took 3 cycles (~5 min each, do them in this order):**
1. `unity … eval --code 'Unity.Burst.BurstCompiler.Options.EnableBurstCompilation = false; …'`, run ONE
   test, re-enable → PASSED. So Burst-only.
2. `rm -rf Library/BurstCache/JIT` + recompile → still NRE (so not [[stale-burst-after-merge]]);
   the Burst toggle above also did not clear it (so not [[bursted-job-layout-not-domain-reload-invalidated]]).
3. `git stash push -- <system.cs>`, recompile, run the non-player test → PASSED on the unmodified
   system; `git stash pop`. So the change itself.
The one structural difference from the sibling that works (`OldShootingSystem`, same lookup, same
helper): its `OnCreate` is NOT `[BurstCompile]`. Removing `[BurstCompile]` from
`OldBeamShootingSystem.OnCreate` → 4/4 pass under Burst; the fast suite stayed 3968/0/20.

**How to apply.** When a Burst-compiled system gains a `SystemAPI.GetComponentLookup`/type handle and
its EditMode tests NRE inside OnUpdate while the managed path passes, drop `[BurstCompile]` from
`OnCreate` (OnCreate runs once; nothing is lost) before hunting further. Verify the built player
still behaves (r10 did). Root cause in Entities' generated `OnCreateForCompiler`/handle assignment
is NOT established — this is an empirical fix.
