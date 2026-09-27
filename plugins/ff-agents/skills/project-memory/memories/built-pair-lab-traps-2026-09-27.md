---
name: built-pair-lab-traps-2026-09-27
description: "081 live desync check (2026-09-27): an UpgradeStep versioned ABOVE the running build re-runs on every join snapshot and reload (a non-idempotent step forks; record a flag in the save); compare_determinism_reports.sh sees only each report's text tail, so use compare_audit_records.py for long/rejoin runs; a live generation drop needs a networked op (solars are not deleteimmediate-able, construction.remove needs bots); modules join a grid by aligned slots, not adjacency."
metadata:
  type: project
---

# Built-pair lab traps, 2026-09-27 (081 live desync check)

- **An upgrade step versioned above the build re-runs on joins and reloads.** Develop was 0.50.0.34
  when spec 081 added `Step0_50_0_35ChargeEnergy`, which multiplies charge by 30. Every save the
  build wrote was stamped .34 < .35, so the step ran again on each load, and MP join snapshots take
  the same load path. The client held 30× the host's stored energy, and power diverged 8
  heartbeats into each epoch. Fix (`dfe58918f`): the save records `ChargeIsStoredEnergy` (codec
  v3), and the step converts only saves without it. **How to apply:** a non-idempotent step must
  either be versioned at or below the build that ships it, or key off a flag the save carries.
  Test the second load, not just the first.
- **The text comparer only sees the tail.** `compare_determinism_reports.sh` reads the
  `[DeterminismAudit]` text mirror, which keeps only a bounded tail per peer. A 9,506-heartbeat,
  two-epoch run compared just 990 heartbeats and still printed NO DIVERGENCE. The
  `# audit-record-v1` Fingerprint records cover every heartbeat, so compare those with
  `scripts/audit/compare_audit_records.py` (pairs on epoch and heartbeat; all fields plus
  `simulationTimeRaw`).
- **A live generation drop needs a networked op that actually lands.**
  `construction.deleteimmediate` rejects solars with `not-immediate-deletable-class`; it only takes
  haulers, ephemeral structures and unbuilt ghosts (`UnbuildValidator.ValidateDeleteImmediate`).
  `construction.remove` only marks for removal, and a marked solar keeps generating until a bot
  deconstructs it. What works is feeding the grid through Power Distributors, then
  `ffauto:setting.powerdistributor|<sx>|<sz>|clear`. The sender transmits its grid's spare power;
  a receiver on the target grid publishes it.
- **Grids join by aligned slots, not adjacency** (`StationConnectionsSystem.SetupConnections`).
  - Solars side by side, a solar under a battery, and a distributor beside a Large Cargo Hold
    each stayed separate grids.
  - Proven shapes: a solar with its top end under a Large Cargo Hold column; a distributor under a
    Large Cargo Hold column. `ValidationScenarios/power/many-to-one.ffbp.txt` gives a zero-idle
    source: a distributor, a Trash Can above it, a solar facing down (direction 2) above the can,
    and a solar facing right (direction 1) on the can's left.
  - Check membership with `ffauto:power.inspect` and the `EnergyInspect` headroom before running a
    leg.
- **Catching a one-heartbeat state.** A 48 kW·s mass-driver pulse lasts 4 heartbeats at 16 UPS, and
  a refusal (`ChargePulseState.Failed`) lasts one. Chains of `ffauto:wait|0.05;ffauto:charge.inspect|x|z`
  sample every heartbeat; 20 s probes never see it.
