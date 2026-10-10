# Time the added code when the bench cannot resolve 1%

**The rule.** When a class 3 FFBox desync PR's before/after bench cannot resolve a 1% change (the run-to-run
spread is wider than the threshold), do not escalate on noise and do not merge on a hunch. Time the code the change
adds directly, on the same big save, and use that as a resolved upper bound. Time it again with the case that
triggers the change present.

**Why (w824, 2026-10-09, PR #1332, the vision fingerprint skipping blueprint-preview children).** The 2-peer
JustPlay bench on BEAST, 4 develop and 4 branch runs interleaved, gave a host heartbeat mean of 123.3 ± 3.6 against
125.3 ± 9.4 ms: a standard error of 5 ms on the delta, against a 1% threshold of 1.2 ms. One branch run (138.9 ms)
carried the whole difference, and the client moved the other way. About 280 runs would have resolved it. Timing
`PrepareC3VisionChunks`, the only main-thread code the change adds, on JustPlay in the editor (50 calls, 1.08 ms
median, every 8th heartbeat) bounded the change at +0.11% on the tick mean, +0.63% on p95 and +0.57% on the frame
median. Timing the vision hash with a held Railgun-like preview found a cost the bench could never show (no preview
in the bench): 47.6 against 42.6 ms, because every one of 45,566 holders paid a `NativeHashSet` lookup. The review
limited the lookup to Parent-bearing chunks (49.9 against 50.0 ms after).

**How to apply.** The class 3 section of `checklists/ffbox-desync-pr.md` lists the steps: load and unpause the save
in the editor, reflection plus `Stopwatch` around each added function, the editor figure as the upper bound,
converted per sample interval; then the triggering case present against absent, interleaved. The PR names which
measurement resolves each number.
