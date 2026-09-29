---
name: beast-shared-machine-perf-ab-side-by-side
description: BEAST is shared by the ffsb sandboxes, and their editors and GPU benches can slow a headless host 30-60x for minutes; judge build-vs-build performance by running the two builds side by side, never one after the other.
---

# Judge build-vs-build performance side by side on BEAST

087, 2026-09-28: after a rebase, the paired audit's headless host ran at 90-260 ms a frame
(5-10 heartbeats/s) where the previous build had held 3.3 ms (2,600+ frames and 160 heartbeats per
10 s). Total CPU read only ~30 % on the 32-thread machine; another sandbox's editor was busy and its
GPU-bench player started mid-run. It looked like a regression in the rebase.

It was the machine. Run one after the other, the old build was clean in one window and slow in the
next. Run **at the same time** (two pairs on different ports, same noise), the two builds paced the
same: p50 3.3 ms, p99 84-168 ms vs 107-169 ms, 126-157 heartbeats per 10 s on both.

- Before calling a pacing change a regression, list the other players and editors
  (`Get-CimInstance Win32_Process -Filter "Name='finalfactory.exe' OR Name='Unity.exe'"`, with the
  command line's project path) and sample per-process CPU (`Get-Counter '\Process(*)\% Processor Time'`).
- Compare two builds by launching both pairs together, twice. Cleanup in
  `run_build_multiplayer_audit.sh` is PID-scoped and each run takes its own port, log dir and build
  dir, so two can run at once.
- Not every sandbox honours `/f/ffsb/gpu-bench.lock`, so holding it does not keep the machine quiet.
- A late-join or first window can differ between runs for reasons of its own; compare the steady windows.

Related: [[feedback-beast-work-goes-through-a-sandbox]], [[fmod-init-assert-kills-headless-client]].
