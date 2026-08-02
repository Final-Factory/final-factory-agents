---
name: determinism-audit
description: Verify multiplayer determinism work — the paired two-editor localhost audit (ParrelSync clone setup incl. the FMOD symlink gotcha, .ff-local-automation.json, per-heartbeat fingerprint comparison) plus the persistent determinism testcases (feature 009) and the wrapper audit scripts (run_join_catchup_audit.sh, run_construction_audit.sh, compare_determinism_reports.sh). Use when verifying any multiplayer/determinism change, running a paired host+client session, comparing determinism reports, or diagnosing a desync/divergence.
---

# Verifying multiplayer work (the determinism harness)

> 📋 **Persistent determinism testcases (feature 009)**: the standing, version-controlled
> regression suite lives under `Assets/Resources/TestRunner/<Subject>/*.playtest` (folders name
> WHAT is tested — Smoke/ConstructionBots/Crafters/Power/Logistics/Mining/Settings — never the run mode).
> One testcase, three run modes: **mode 1** run-once golden (`FinalTestRunner.RunAllTests`),
> **mode 2** two-editor divergence (`./run_determinism_testcases.sh`), **mode 3** same-editor
> run-twice divergence with snapshot-restore (`DeterminismTestRunner.RunDeterminismGate` — runs
> in the normal play-mode loop, no build/clone). See the "Persistent determinism testcases"
> section of `Documentation/Determinism-Test-Strategy.md` and
> `specs/009-determinism-testcase-harness/contracts/determinism-verdict.md`.

> ⚠️ **A mode-3 divergence is not automatically a SIM defect — check command TIMING first**
> (feature 042, 2026-07-25). Before feature 042, `ffauto:heartbeats|N` advanced the sim one
> heartbeat per rendered **frame** but chains awaited a **wall-clock** estimate; below ~10 fps the
> next command fired mid-pump and phase-shifted otherwise identical fingerprint streams. Current
> source registers the manual pump's `ChainCompletion`
> (`LocalMultiplayerAutomationCommandRunner.cs:1017-1019`) and both chain executors claim and await
> that completion before proceeding. The check below remains useful for historical reports,
> unmerged branches, and any future regression of that ordering.
> 🔑 **How to check**: the Editor.log interleaves `[DeterminismAudit][Heartbeat N]` lines with
> `[determinism] setup '<cmd>'` lines, so scanning it while tracking the last-seen heartbeat gives
> **the heartbeat each command actually fired at**. Compare that against the testcase's pump
> schedule before hunting a simulation bug. Tell-tale signature: identical stream lengths, and the
> same fingerprint sequence phase-shifted rather than genuinely different values.
> 🔑 **`DeterminismTestRunner.TestcaseFilter`** (committed value `null` = whole corpus) restricts the
> gate to one testcase — a targeted investigation costs ~3 minutes instead of the ~10-50 minute
> sweep. A successful filtered investigation ends NUnit **Ignored**, not Passed, and is **not** a
> gate result; a divergence still fails normally.
> 🔑 **Throttling the editor to reproduce it needs a HOLDER, not a one-shot**: the game caps its own
> frame rate at boot (`DisplaySettingsController`, "Capping FPS on system start"), so re-apply
> `QualitySettings.vSyncCount = 0` + `Application.targetFrameRate = <n>` every ~10 s for the whole
> play session via `unity-cli eval_file`.

Two complementary layers:

1. **EditMode determinism tests** (`Assets/Tests/Multiplayer/`) — e.g. `DeterminismStateFingerprintTest`, `HeartbeatCatchUpTest`, `PlayerPositionReplicationTest`. Run via the MCP bridge (see **Running tests** in CLAUDE.md). The paired audit below still uses filesystem channels (`.ff-local-automation.json`, the report files, the comparison scripts).
2. **Paired localhost audit** — runs a real host+client play session and compares per-heartbeat state:
   - Requires a sibling **ParrelSync clone**. **The clone directory is ALWAYS `<this project's folder name>_clone_0`** (ParrelSync convention), i.e. the sibling dir = base working directory + `_clone_0`. Its `Assets`/`ProjectSettings` symlink the originals, so code is shared — verify with `ls -l ../<this project's folder name>_clone_0/Assets` → must point at `…/<this project's folder name>/Assets`.
     - ⚠️ **The clone also needs a manual `FMODProject` symlink** (`ln -s ../<base>/FMODProject ../<base>_clone_0/FMODProject`) — ParrelSync only links `Assets`/`ProjectSettings`/`Packages`, but the FMOD banks live at the project root (`FMODStudioSettings.asset` `sourceBankPath: FMODProject/...`). Without it the clone's FMOD bank-load exceptions look non-fatal but **silently break the multiplayer save-apply**: the clone connects (`IsConnectedClient=True`) yet its world never materializes (`players=0, placeables=0`, stuck at `joining-localhost`). Headless build audits are unaffected (banks ship in StreamingAssets) — easy to misdiagnose as a join/netcode bug.
   - ⚠️ **Multiple project copies exist side by side** (e.g. `FinalFactory`, `FinalFactory2`), each with its own `_clone_0` doing its own updates. A wrong-named dir is a **different project's** clone — never write triggers/configs there. Always derive the clone path from the current project folder name (`$(basename "$PWD")_clone_0`) and confirm the `Assets` symlink target before using it.
   - Write `.ff-local-automation.json` to **both** project roots (host = repo root, client = clone) with `Enabled`/`AutoStartInEditor` true, a unique `Label`, asymmetric `PostConnectDelayMs` (host longer so the client writes its report first), and an optional `PostReadyCommand` (e.g. `ffauto:movement.hold|x|z|seconds`, `ffauto:mining.startnearest`). Each open editor's 1s poller auto-starts play mode. Menu items under `Final Factory/Multiplayer/Automation/` do the same.
   - `DeterminismFingerprintSystem` writes a per-heartbeat fingerprint (station-grid, power, player inventories, player simulation position) into reports under `~/Library/Application Support/Never Games/finalfactory/DeterminismAudit/`.
   - Compare the host/client reports with `compare_determinism_reports.sh <host.log> <client.log>` → prints the first diverging heartbeat or "NO DIVERGENCE".
   - `run_join_catchup_audit.sh` wraps the whole flow (recompile both editors, drive a moving-player paired session, assert per-heartbeat `playerSimPos` alignment) as a one-command regression test for the join-time heartbeat catch-up. It recompiles each editor by invoking that root's `run-tests.sh fast` (which waits via `wait_for_test_results.sh`) over the `run-tests-fast.trigger` / `test-results.txt` file-watch channel (`Assets/Editor/TestRunnerTrigger.cs`) — the one place that fallback mechanism is still required. Note: back-to-back paired runs can contaminate each other (stale play sessions) — restart both editors for a clean run.
   - `run_construction_audit.sh` is the construction-lane sibling (feature 005): by default a post-join `construction.place` task-symmetry check; `MODE=build` provisions bot+items through the deterministic queue and asserts the full place→build→finalize loop cross-peer (completion witness on cbots/grids); `MODE=build PROVISION=preconnect` provisions PRE-join so the spawned fleet bot rides the join save (the 005 R3.5 lanes).
   - 🔑 **The dwell is WALL-CLOCK but every acceptance bar counts SHARED HEARTBEATS** (feature 039, 2026-07-24). Multiplayer only reaches 8 UPS if the peers keep up, so on a slow or loaded machine the same dwell yields far fewer heartbeats: the identical `MODE=place` window produced **234** shared heartbeats on one session and **102** on another *with no code change between them*. A short window makes an audit look like it passed when it merely did not run long enough to disagree. **Override `HOST_DWELL_MS` / `CLIENT_DWELL_MS`** to buy the heartbeats a criterion needs instead of quietly accepting a short run — e.g. `MODE=build HOST_DWELL_MS=100000 CLIENT_DWELL_MS=88000 ./run_construction_audit.sh` gave **323** shared heartbeats where the 60 s default gave 183. `CLIENT_DWELL_MS` must be **less than** `HOST_DWELL_MS` (hard-enforced, exit 2) so the host outlives the client and the shared window is not truncated.
   - 🔑 **`timed out waiting for test-results.txt (editor closed / in play mode?)` in phase 1 usually means NEITHER** (feature 039, 2026-07-24). Both editors are triggered CONCURRENTLY, so two full EditMode suites plus domain reload and test-framework init contend for the same cores. **Before believing the message, `cat <root>/test-results.txt` in both roots** — if it says `PASSED`, the suite simply finished after the script gave up, and you only need to re-run (the compile is warm the second time). The ceiling is now `RECOMPILE_WAIT_TICKS` (240 ticks × 2 s = 480 s default), raised from a fixed 180 s that three consecutive runs overran on a loaded machine.
   - **Launch long audits detached**: `nohup ./run_construction_audit.sh > log 2>&1 < /dev/null & disown`, and monitor the LOG FILE rather than the job — a tracked background task was reaped mid-phase-1 and reported as killed with no audit failure at all. (`setsid` does not exist on macOS.) Wait for BOTH editors to report ready + `playMode: stopped` (`scripts/unity-cli.sh command --project-path <abs> editor_status`) before launching the next audit; a preceding paired session takes time to wind down.
   - **Gotcha**: the ParrelSync clone runs its own `Library/ScriptAssemblies` and does NOT auto-recompile code edits made after it booted. Before any paired run after a code change, force its recompile **through the MCP bridge** — the clone is its own connected instance: find it in `mcpforunity://instances` by its `path` (`…/<this project's folder name>_clone_0/Assets`), `set_active_instance` to that `Name@hash`, call `refresh_unity` (or `run_tests` on it), then `read_console` on the clone to confirm a clean compile (no `error CS`) before pinning back to this project. (First run on stale code otherwise silently uses the old build.)

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
   with the repo at `~/nevergames/FinalFactory`. Proven 2026-07-11: M5 Pro 18-core vs M3 Pro 11-core,
   NO DIVERGENCE on movement (209 hb) + heavy construction (461 hb, 12 lines/8 bots). Proven
   2026-07-26 on Wittlebase: 681 shared heartbeats from heartbeat 1 with zero authoritative
   divergence, while 668 raw float-heavy research diagnostics differed and their normalized
   non-float state had zero differences
   (`specs/038-join-desync-crafter-deploy/plan.md`, session handoff 2026-07-26k). ⚠ Known limits
   (021 backlog): a run that dies abnormally can strand an editor in Play mode (reset it manually — no
   remote-MCP reach); the rolling report window evicts early heartbeats on long busy runs (shorten
   `DURATION_S` to keep a burst in-window). The `.110` checkout currently can fetch over its
   non-interactive SSH session; fast-forward it with the exact command in
   `Documentation/Two-Machine-LAN-Dev-Pair.md:34-48` when the pre-flight hashes differ.
