---
name: deferred-job-array-in-ijobentity-read-garbage
description: "A NativeList from EntityQuery.ToEntityListAsync passed into an IJobEntity as list.AsDeferredJobArray() read garbage (a Burst NullReferenceException in some runs, no matches in the rest); passing the NativeList itself as a [ReadOnly] field and calling .AsArray() inside the job worked (w1200, 2026-10-13)."
metadata:
  type: project
---

w1200 (`AncientPortalCollisionSystem`, game repo #1629): the system queued the portal list with
`_portalQuery.ToEntityListAsync(World.UpdateAllocator.ToAllocator, Dependency, out var ready)` and handed the job
`Portals = list.AsDeferredJobArray()` (a `NativeArray<Entity>` field of an `IJobEntity`, scheduled on
`JobHandle.CombineDependencies(Dependency, ready)`). Eight new EditMode tests failed: no portal was ever found, and
some runs logged `NullReferenceException ... thrown from a job compiled with Burst` from
`JobChunkProducer<AncientPortalCollisionJob>.ExecuteInternal`. Changing only the field to
`[ReadOnly] public NativeList<Entity> Portals` (passing the list, reading `Portals.AsArray()` in `Execute`) made all of
them pass. Observed once, the cause not traced into the job system: the deferred array was evidently not resolved
for that job.

**How to apply:** give an `IJobEntity` or `IJobChunk` the `NativeList` itself, not `AsDeferredJobArray()` (that
pattern belongs to `IJobParallelForDefer`). A job that finds nothing on data you know is there, plus a Burst NRE
in `ExecuteInternal`, points here.
