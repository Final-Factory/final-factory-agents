---
description: The built-player audit report keeps about the last 2,600 fingerprint lines per peer, and the dwell runs AFTER the command chain; a long dwell pushes the scenario and the movement out of the compared window. Keep the dwell short. A 12k-character command line does not launch.
---

# The paired audit compares only the last ~2,600 heartbeats (w169/w170, 2026-10-01)

- `run_build_multiplayer_audit.sh` compares the heartbeats both reports hold. Each report keeps roughly
  the last 2,600 fingerprint lines (about 160 s at 16 UPS). `SHARED HEARTBEATS: firstHeartbeat=1544`
  means everything before 1544 was not compared.
- `--host-delay-ms` / `--client-delay-ms` start when the peer's post-ready chain has FINISHED. With a
  130 s chain and a 190 s dwell the window held only idle time: `NO DIVERGENCE` on 2,600 heartbeats and
  `FAIL [playerSimPos]: only 1 distinct value(s)`, because the movement was before the window.
- Recipe: dwell 20000 / 12000 ms (the client writes first), chains of at most about 140 s, the action
  and a `movement.hold` inside them. To find where an action landed, take the nearest
  `[DeterminismAudit][Heartbeat N]` tag above its line in `Host.log`.
- On Windows the host's chain starts at host-ready, before the client joins: put `ffauto:wait|25` or
  more first if the action must be in the shared window.
- A local injector on purpose (`inventory.remove`) differs in `playerInvTotals`; re-run
  `compare_determinism_reports.sh` with `REPORT_ONLY_FIELDS=playerInvTotals` to gate everything else.
- A `--host-cmd` with 16 `construction.place|<704-char blueprint>` entries (about 12,000 characters)
  never started the host: empty `Host.log`, `host never logged 'status host-ready'`. Twelve worked.
- `desync.forceresync|all` mid-chain is compared across both epochs (`firstEpoch=1 .. lastEpoch=2`).
- `--host-preconnect-cmd` did not hold the client back until its chain finished: the client joined
  during the chain's first `wait`. Do not rely on it to stage a world state for the join.
