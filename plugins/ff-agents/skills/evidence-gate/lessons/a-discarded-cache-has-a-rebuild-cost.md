---
name: a-discarded-cache-has-a-rebuild-cost
description: "Before a change or design throws away build state (Unity Library caches such as BurstCache, BuildCache, ScriptAssemblies or Bee, CI caches, build outputs) or adds a rebuild, measure the CPU and wall time of the rebuild it causes and weigh it. Prune only stale entries; a whole wipe is a last resort; the PR states the measured rebuild cost. Build and worker machines have no spare CPU."
date: 2026-10-31
---

# A discarded cache is a rebuild: measure it and weigh it before it ships

**Rule.** Any change or design that deletes build state (Unity `Library` caches: `BurstCache`, `BuildCache`,
`ScriptAssemblies`, `Bee`; CI caches; build outputs) or adds a rebuild step must, before it ships:

1. **Measure the rebuild it causes**, CPU time and wall time (a cold Unity start of that project, or the build
   step it adds), on the kind of machine that pays for it. Not a guess, not "should be quick".
2. **Weigh it** against what the delete or the extra build buys (GB freed, a stale cache avoided).
3. **Prefer pruning only stale entries** (old, unreferenced, over a size budget by age) to wiping a cache. A
   whole wipe is a last resort, and the design says why pruning cannot do it.
4. **State the measured rebuild cost in the PR**, beside the saving.
5. **Count the whole of it.** Deleting one cache usually forces its siblings to rebuild too (the Burst cache
   goes, then the asset import and script compile follow): measure the cold start, not one folder.

**Why.** The build and worker machines usually have no spare CPU. LothDesktop is almost always at full CPU, and
a cold Unity start is slow, so every wipe is paid for by every other job on that machine. Lothsahn made this
correction twice:

- w2275 (FFBox refreshing its caches after a release): the first design ran a separate post-release cache
  rebuild, about 25 minutes of build CPU. Lothsahn: "It's doing a separate build?  It shouldn't do that as that
  wastes CPU.  Also, every OS cache should get updated by its own release build". The release build already
  produced the cache; saving it there cost nothing extra (#2611, merged).
- w2752 (the portal's clean-up, ff-factory PR #791): it deleted a sandbox's `BurstCache` and `BuildCache` whole
  once they passed 6 GB. Lothsahn: "Doesn't deleting the burst caches make the next startup really slow and use a
  lot of CPU?" and "Not just the burst cache, but all the caches.  A cold unity station is quite slow so we
  should make sure to not do it often.  LothDesktop is almost always at full CPU and doesn't have any to spare."

Both times the saving (disk, freshness) was weighed and the CPU cost was not.

**How to apply.**

- At design time, before the first edit, write down which state is discarded or rebuilt, how often, and on which
  machine. A clean-up that runs daily and wipes a cache means a cold start daily.
- Look for a way that rebuilds nothing extra: reuse the build that already runs (each OS's own release build
  saves its own cache), or prune entries older than N days or beyond the ones the current project version uses.
- Measure the cold cost on the target machine class (`unity-slot run`, a timed ticket per `checklists/bench.md`
  when the number is a timing), and put CPU-minutes and wall-minutes in the PR.
- If a wipe is still the choice, say what pruning was tried or why it cannot work, and how rarely the wipe runs.

Related: [delete checklist](../checklists/delete.md) item 7, [clean up after yourself](clean-up-after-yourself.md).
