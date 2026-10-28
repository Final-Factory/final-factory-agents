---
name: heartbeat-frame-trim-w2394
description: What w2394 (Wittlebase heartbeat-frame trim, lothlaptop, 2026-10-27/28) measured: where a heartbeat frame's time goes, a collision ApplyJob split that bought nothing, raw profiler log size, and the .mat churn that blocks switch_branch.
---

# Heartbeat-frame trim: what w2394 measured

**Where the time goes** (lothlaptop, master 8bfcb18dc1 development player, Wittlebase save, timed run tr_84d26d9e9d).
A heartbeat frame is 4.86 ms longer than a frame without one. About 1.9 ms is fixed-group main-thread work spread
thinly over many systems (per-system overhead, no single big one). About 1.85 ms is job waits. The top serial job on
the critical chain was `FpCollisionWorldBuildSystem`'s ApplyJob at 0.285 ms per heartbeat. Removing one wait only moves
it to the next system that syncs (w2361, measured on biscuit).

**Splitting the collision ApplyJob bought nothing** (tr_fefb930bb3, lothlaptop, one build, 6 rounds).
- **The change:** ScanJob, which runs in parallel, wrote a changed body that keeps its grid cells straight into
  `Bodies[slot]`. Only bodies that changed cells went through the serial ApplyJob.
- **Fixed work per heartbeat:** 3.66 ± 0.16 ms with the split, 3.51 ± 0.15 ms without (`-ffFpSerialApply`).
- **Frame:** 17.20 ms against 16.93 ms.
- **Caveat:** a person used the laptop during every leg.
- **Result:** dropped and never merged (branch `sandbox/slot1-w2394-apply`, commit efb29e0840). Don't redo it. A
  0.3 ms serial job on the chain is not where a heartbeat frame's time is.
- **Cheap A/B pattern worth reusing:** a `-ffXxx` switch, read once in `OnCreate`, that restores the old path. One
  build is then timed as two variants (the `-ffFpFullRebuild` and `-ffFpSerialApply` style).

**A raw profiler log is too big to come back from a timed run.**
- A `-ffPerfMarkers` raw capture of Wittlebase writes about 12 MB a second: 8 s came to about 96 MB, and 20 s × 2
  variants × rounds to 469 MB.
- `timed_run` returns at most 200 MB of logs, so the logs of that run never came back.
- For a raw capture, use `rounds: 1` and `sample_s: 8`.
- Writing the log costs about 1.1 ms a frame, so never compare frame times from a capture run with a run without one.

**`switch_branch` is refused after the editor quits.** Unity reserializes some `.mat` files and a TMP font asset on
quit, and the dirty tree blocks the switch. Those files are not your edits: `git checkout -- <them>`, then switch.
