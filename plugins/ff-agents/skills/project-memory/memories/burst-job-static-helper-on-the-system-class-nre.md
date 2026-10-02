---
name: burst-job-static-helper-on-the-system-class-nre
description: "A private static helper declared on the system class and called from its nested Burst job compiled with no error and threw NullReferenceException at run time under Burst (passed with Burst off). Moving the helpers inside the job struct fixed it. Seen in GridWarningCheckerSystem (w180, PR 907)."
metadata:
  type: project
---

# A static helper on the system class, called from its Burst job = NRE under Burst (2026-10-01, w180)

**Symptom.** After `GridWarningCheckerSystem` gained two small helpers (`IsPowerOrStabilityWarning`,
`IsPlayerOrderWarning`) as `private static` methods of the system class, called from the nested
`[BurstCompile]` job, every icon test threw `NullReferenceException` inside the job, the existing
`BurstPowerWarningTest` included. No Burst compile error, no `error CS`. With
`BurstCompiler.Options.EnableBurstCompilation = false` the same tests passed.

**Fix.** The helpers moved into the job struct (still `private static`), with a comment saying why.
All tests pass under Burst.

**How to apply.** A helper a Burst job calls lives in the job struct or in an unmanaged static
utility type, never on the system class that holds the job. If a new test NREs only under Burst
right after a refactor, check where the job's callees are declared before the other Burst causes
([[stale-burst-after-merge]], [[bursted-job-layout-not-domain-reload-invalidated]],
[[burst-oncreate-plus-new-systemapi-lookup-nre]]).

The root cause inside Burst was not established: this is an empirical fix, confirmed by one
Burst-off run and by the change of declaring type alone.
