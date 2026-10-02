---
description: Host and client post-ready chains start on their own clocks; ffauto:wait offsets race. Use movement.hold for the offset, a fresh label per run, and an ffnightly scenario for order-sensitive checks.
---

# Paired built-player audit: the two peers' command chains race

From w161 (research queue ops, PR #881, 2026-10-01). `run_build_multiplayer_audit.sh --host-cmd/--client-cmd`
runs one chain per peer, each on its own clock.

- **`ffauto:wait|N` offsets alone raced.** A host chain starting `wait|4` and a client chain starting `wait|7`
  ran the client's first op at heartbeat 8 and the host's at 14. The run was green on every heartbeat and proved
  almost nothing: every later op was refused, identically, on both peers. Read the host log for
  `rejecting` lines before believing a green run exercised your ops.
- **Use `ffauto:movement.hold|x|z|seconds` for the initial cross-peer offset.** It is wall-clock, and it also
  satisfies the script's `playerSimPos` liveness gate, which FAILS (exit 5) a run in which no player moved
  ("only 2 distinct value(s)"), even with `NO DIVERGENCE` on every heartbeat.
- **Never reuse a `--label`.** A second run under the same label ended `ERROR: missing report(s) —
  host='none' client='none'`, although both players ran and logged the whole sequence.
- **`--host-preconnect-cmd` does not order ops like a post-ready chain.** `research.setactive;heartbeats|8;
  research.queue` applied the add before the set-active, so the add was skipped as locked.
- **For an order-sensitive two-peer check, write an ffnightly scenario instead.** Each step names its peer,
  `poll` + `equals` on `ffauto:observe.state|<scope>` asserts every peer's state (the result is parsed into
  `data`, so the path is `data.data.<field>`), `"windowed": true` + `screenshot` steps give both screens, and
  `"peers": ["host", "a"]` with a two-peer `--lab` file keeps it to two players. Then run the paired audit once
  for the per-heartbeat verdict.
- **The determinism fingerprint does not cover `ResearchState`.** A green fingerprint says research ops forked
  nothing else; compare the queue itself through the research snapshot and the `ResearchQueueNetworkOperation
  -> DoOperation` records in the two audit reports.
- **A demo-locked refusal on development players:** `ffauto:research.demolock|on` (DevOnly) sets the
  per-process `GameMetaState.IsDemo` the host's validation reads; no development build is a demo.
- **The client joins part-way through a `--host-preconnect-cmd` chain, and its `wait|N` seconds are not
  heartbeats** (w196, 2026-10-02): order the peers with `ffauto:heartbeats|N` on both. Details:
  [[barge-scenarios-audits-and-clips-lessons-2026-10-02]].
