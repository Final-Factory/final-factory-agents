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
