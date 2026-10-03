---
name: bursted-job-layout-not-domain-reload-invalidated
description: A Bursted job whose struct layout changed is not invalidated by a domain reload alone — a distinct symptom (UNKNOWN_OBJECT_TYPE) from the JIT-cache staleness in stale-burst-after-merge; a nested unused ComponentLookup job field must still be valid
metadata:
  type: project
---

Distinct from [[stale-burst-after-merge]]'s "wipe `Library/BurstCache/JIT`" finding (that one
covers stale native code surviving a MERGE, diagnosed via NRE/BC1054): a job struct whose layout
changed in the SAME session was seen to symptom as `UNKNOWN_OBJECT_TYPE ... has not been
assigned` rather than an NRE, and a plain domain reload did not clear it. Toggling
`BurstCompiler.Options.EnableBurstCompilation` off then back on (not just wiping the JIT cache)
resolved this specific symptom. Treat the two as separate failure signatures needing separate
fixes — if one doesn't clear the symptom, try the other before assuming the code itself is wrong.

Separately: a nested `ComponentLookup` field inside a job struct must be a REAL, valid lookup
even on a code path where the job never reads it — leaving it `default` aborts the job under
Burst's safety-handle reflection at schedule time, regardless of whether the field is ever
touched.

**How to apply:** `UNKNOWN_OBJECT_TYPE ... has not been assigned` after a struct-layout change →
try the `EnableBurstCompilation` off/on toggle before reaching for a JIT cache wipe. Always
populate every `ComponentLookup` job field with a real lookup, never `default`, even if unused on
some paths.

**A third signature (2026-10-02, w195):** after a field was inserted into a Bursted job struct, the job read
a bool at its old offset and tests failed with nonsense values, with no error at all. A domain reload and the
`EnableBurstCompilation` toggle did not clear it. Stopping the editor, moving `Library/BurstCache/JIT` aside and
restarting did. Wait for Burst to go idle before the next run (`BurstLoader.BurstProgressId` is -1, or
`Progress.Exists(id)` is false).

**A fourth signature (2026-10-03, w225):** after a `BufferLookup` field replaced a `DynamicBuffer` field in an
`IJobEntity` and a `ComponentLookup` was captured into a `Job.WithCode`, EditMode tests failed with a
`NullReferenceException` at `JobChunkProducer.ExecuteInternal` (`IJobChunk.cs:374`), and the lambda job silently
spawned nothing. The same tests passed with Burst off; turning it back on with synchronous compilation did not
clear it. The stack's module hash named a `Library/BurstCache/JIT/<hash>.dll` dated an hour BEFORE the edit (the
session had shared the Library with batchmode player builds). A plain editor restart cleared it. Reading that DLL's
timestamp is the quick check that it is stale native code and not the change.
