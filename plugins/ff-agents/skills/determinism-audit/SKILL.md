---
name: determinism-audit
description: Verify multiplayer determinism work — the paired two-editor localhost audit (ParrelSync clone setup incl. the FMOD symlink gotcha, .ff-local-automation.json, per-heartbeat fingerprint comparison) plus the persistent determinism testcases (feature 009) and the wrapper audit scripts (run_join_catchup_audit.sh, run_construction_audit.sh, compare_determinism_reports.sh). Use when verifying any multiplayer/determinism change, running a paired host+client session, comparing determinism reports, or diagnosing a desync/divergence.
---

# Verifying multiplayer work (the determinism harness)

> 📇 **Which script for which scenario**: the game repo's
> **`Documentation/Audit-Script-Index.md`** indexes every `run_*_audit.sh` (30+) and the
> `scripts/` audit utilities — one sourced row each. Start there when picking a lane.
> 🪤 **Dated traps and hard-won triage recipes** live in **`gotchas.md`** next to this file —
> read its TOC before diagnosing any divergence, "missing report", flaky gate, or clone
> weirdness. The recipes there are load-bearing, not history.

> 📋 **Persistent determinism testcases (feature 009)**: the standing, version-controlled
> regression suite lives under `Assets/Resources/TestRunner/<Subject>/*.playtest` (folders name
> WHAT is tested — Smoke/ConstructionBots/Crafters/Power/Logistics/Mining/Settings — never the run mode).
> One testcase, three run modes: **mode 1** run-once golden (`FinalTestRunner.RunAllTests`),
> **mode 2** two-editor divergence (`./run_determinism_testcases.sh`), **mode 3** same-editor
> run-twice divergence with snapshot-restore (`DeterminismTestRunner.RunDeterminismGate` — runs
> in the normal play-mode loop, no build/clone). See the "Persistent determinism testcases"
> section of `Documentation/Determinism-Test-Strategy.md` and
> `specs/009-determinism-testcase-harness/contracts/determinism-verdict.md`.

Two complementary layers, plus the cross-machine harness:

1. **EditMode determinism tests** (`Assets/Tests/Multiplayer/`) — e.g. `DeterminismStateFingerprintTest`, `HeartbeatCatchUpTest`, `PlayerPositionReplicationTest`. Run via the MCP bridge (the `editor-ops` skill). The paired audit below still uses filesystem channels (`.ff-local-automation.json`, the report files, the comparison scripts).
2. **Paired localhost audit** — runs a real host+client play session and compares per-heartbeat state:
   - Requires a sibling **ParrelSync clone**. **The clone directory is ALWAYS `<this project's folder name>_clone_0`** (ParrelSync convention), i.e. the sibling dir = base working directory + `_clone_0`. Its `Assets`/`ProjectSettings` symlink the originals, so code is shared — verify with `ls -l ../<this project's folder name>_clone_0/Assets` → must point at `…/<this project's folder name>/Assets`. The clone ALSO needs a manual `FMODProject` symlink, and a wrong-named sibling dir is a DIFFERENT project's clone — both traps in `gotchas.md` §Clone setup.
   - Write `.ff-local-automation.json` to **both** project roots (host = repo root, client = clone) with `Enabled`/`AutoStartInEditor` true, a unique `Label`, asymmetric `PostConnectDelayMs` (host longer so the client writes its report first), and an optional `PostReadyCommand` (e.g. `ffauto:movement.hold|x|z|seconds`, `ffauto:mining.startnearest`). Each open editor's 1s poller auto-starts play mode. Menu items under `Final Factory/Multiplayer/Automation/` do the same.
   - `DeterminismFingerprintSystem` writes a per-heartbeat fingerprint (station-grid, power, player inventories, player simulation position) into reports under `~/Library/Application Support/Never Games/finalfactory/DeterminismAudit/` (macOS; Windows: `~/AppData/LocalLow/Never Games/finalfactory/DeterminismAudit/`).
   - Compare the host/client reports with `compare_determinism_reports.sh <host.log> <client.log>` → prints the first diverging heartbeat or "NO DIVERGENCE". **Never accept a verdict from a partial window** — see `gotchas.md` §Full-window rule before believing ANY diagnosis.
   - `run_join_catchup_audit.sh` wraps the whole flow (recompile both editors, drive a moving-player paired session, assert per-heartbeat `playerSimPos` alignment) as a one-command regression test for the join-time heartbeat catch-up. It recompiles each editor by invoking that root's `run-tests.sh fast` (which waits via `wait_for_test_results.sh`) over the `run-tests-fast.trigger` / `test-results.txt` file-watch channel (`Assets/Editor/TestRunnerTrigger.cs`) — the one place that fallback mechanism is still required. Note: back-to-back paired runs can contaminate each other (stale play sessions) — restart both editors for a clean run.
   - `run_construction_audit.sh` is the construction-lane sibling (feature 005): by default a post-join `construction.place` task-symmetry check; `MODE=build` provisions bot+items through the deterministic queue and asserts the full place→build→finalize loop cross-peer (completion witness on cbots/grids); `MODE=build PROVISION=preconnect` provisions PRE-join so the spawned fleet bot rides the join save (the 005 R3.5 lanes). Dwell sizing (wall-clock vs shared heartbeats) and the phase-1 timeout trap: `gotchas.md` §Wrapper-script traps.
3. **Cross-machine audit (feature 021)** — `run_cross_machine_audit.sh` runs a host on THIS machine
   and a client on ANOTHER LAN machine (over SSH) and compares per-heartbeat fingerprints. This is
   the ONLY way to catch desyncs that only appear across genuinely different hardware (different CPU
   core counts / Job-System scheduling) — a single box can't. One command, no MCP:
   `SCENARIO=movement|construction|save [SAVE=Wittlebase] [LINES=12 BOTS=8 DURATION_S=60] [MIN_HB=0] [CLIENT_HOST=10.0.0.110] ./run_cross_machine_audit.sh`
   (exit 0 = NO DIVERGENCE). It pre-flights (SSH, same-sim-commit, free port, no stale state), writes
   both `.ff-local-automation.json` configs, waits for both reports, `scp`s the client's, compares
   with `compare_determinism_reports.sh`, and always cleans up (configs + play-mode `.mat` nulling on
   both machines while preserving material changes that were already dirty). `SCENARIO=save`
   compares from the first shared heartbeat by default; use `MIN_HB` only when an investigation
   explicitly needs a later lower bound (`run_cross_machine_audit.sh` `build_scenario/save` and
   `cleanup()`). Uses direct-IP UnityTransport — **no Steam needed** (the game runs Steam-logged-out
   gracefully). Prereqs: both editors OPEN + idle in Edit mode, same sim commit, client SSH-reachable
   with the repo at `~/nevergames/FinalFactory`. Proven runs + known limits: `gotchas.md`
   §Cross-machine.

**Before any paired run after a code change**: the clone does NOT auto-recompile — force it
through the MCP bridge and confirm a clean compile on BOTH editors first (`gotchas.md` §Clone
stale assembly). **Long audits**: launch detached and monitor the log file, not the job
(`gotchas.md` §Wrapper-script traps).
