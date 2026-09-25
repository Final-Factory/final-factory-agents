---
name: burst-string-guard-baseline-follows-renames
description: "BurstManagedStringGuardTest's KnownPreExistingDebt baseline is an exact-match set keyed by 'assembly|declaringType|methodName#paramCount'; renaming a listed Burst job method (even for an unrelated reason) fails the test's 'no longer reproduces' assertion until the baseline entry is renamed in the SAME commit — this is a name-matching artifact, not proof the underlying defect changed."
---

# BurstManagedStringGuardTest baseline follows renames

`Assets/Tests/Core/BurstManagedStringGuardTest.cs`'s `KnownPreExistingDebt` is a frozen list of
known BC1016-class sites (a managed string built inside a `[BurstCompile]` path — compiles fine
in the editor's lazy Burst drain, fails a player build that compiles every entry point up front),
keyed `"assembly|declaring type full name|method name#param count"`. The assertion is exact-match
in BOTH directions: a NEW site not in the list fails the test, and a LISTED site that no longer
reproduces — because it was fixed, OR because it was simply RENAMED — also fails ("these
`KnownPreExistingDebt` sites no longer reproduce — remove them from the baseline").

Renaming a Burst job method that appears in the baseline, even for a reason unrelated to
BC1016 — e.g. 074 T169's `StationConnectionsJob.Execute` → `ConnectEntity`
(`e08b384ca`, part of [[same-heartbeat-processing-order-desync-class]]) — changes its
`#paramCount` key and trips the "no longer reproduces" assertion. Update the baseline entry
(`Execute#N` → `ConnectEntity#N`) in the SAME commit as the rename, not a follow-up.

This is purely a name-matching artifact of the deliberately exact-set baseline design (per the
test's own header comment: a looser count-only check would hide a real new violation swapped in
for a coincidentally-renamed fixed one) — it says nothing about whether the method's actual
BC1016-class defect was touched.
