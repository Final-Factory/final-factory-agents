# Determinism-audit gotchas and triage recipes

Dated, hard-won findings. Each entry names the feature/date it came from; the recipes remain
load-bearing for future runs even where the original defect is fixed.

## TOC

- [Full-window rule: never diagnose from a partial window](#full-window-rule) (052)
- ["Missing report(s)" is NOT a stuck editor](#missing-reports) (045)
- [Divergence triage: check command TIMING first](#command-timing) (042)
- [TestcaseFilter: targeted mode-3 investigation](#testcasefilter)
- [Throttling the editor needs a holder](#fps-holder)
- [Clone setup: FMOD symlink + wrong-dir traps](#clone-setup)
- [Clone stale assembly: force the recompile](#clone-stale-assembly)
- [Wrapper-script traps: dwell sizing, phase-1 timeout, detached launch](#wrapper-script-traps) (039)
- [Quarantined-testcase gate flake: the flip rule](#quarantine-flip-rule) (pre-011, recipe retained)
- [Cross-machine: proven runs + known limits](#cross-machine) (021/038/045)

## Full-window rule: never diagnose from a partial window {#full-window-rule}

(Feature 052, 2026-07-30 — the same trap burned the lane TWICE.) The corpus comparator reports
only the FIRST divergence, which can hide the real defect: the 052 hauler triage confidently
claimed a divergence "exactly one heartbeat wide" that was actually e1 hb1 MISMATCH, hb2 MATCH,
hb3-12 MISMATCH with the client hash FROZEN — fixing only the first-heartbeat cause would have
moved the fork hb1→hb3 and left the testcase red. Second instance: "epoch 2 ran 260/260 clean →
recovery re-anchors correctly" was FALSE — the "clean" claim came from a partial-window diff,
and a re-diff found `combat` mismatches at e2 hb9-14. **Always extract and diff per-heartbeat
hashes from BOTH `*-report.log` files over the FULL window before believing any diagnosis** —
and remember an epoch window in which no ops actually fired proves nothing about the surface
("clean" windows are only evidence when the ops that could disagree actually ran).

## "Missing report(s)" is NOT a stuck editor {#missing-reports}

(Feature 045, 2026-07-27.) A completed paired run and a genuinely stuck editor can produce
IDENTICAL script output — historically, `ERROR: missing report(s)` after the full wait loop
usually meant report **discovery** failed, not the run (045's `legacy-<label>` report renaming
broke the old filename glob in 28 scripts; it cost a session three "environment non-result"
attempts and a false written diagnosis). All `run_*_audit.sh` now discover via `da_find_report`
(`determinism_audit_lib.sh`), which matches LABEL + the report's own `role=` header (filenames
lie: a `MODE=client` run's HOST report contains "client" in its name). **The diagnostic lesson
stands for any report-discovery failure: before concluding an audit run failed for environment
reasons, look in the `DeterminismAudit/` output dir for reports matching the label. If they
exist, the run succeeded — evaluate them directly (source `determinism_audit_lib.sh`, use
`da_find_report` / `da_assert_field_aligned`, which key off file CONTENT) instead of restarting
editors.**

## Missing reports on BOTH sides: check for a leaked UDP port first {#port-leak}

(2026-08-07, cost three audit attempts.) `ERROR: missing report(s) — host='none' client='none'`
on a CLEAN start (phase-1 suites green on both editors) with the clone left stuck in play mode
is the signature of the HOST failing to bind its transport: the client's console shows
`Failed to connect to server` / `[MP join] ... transport failure`, and the host's shows
`Failed to bind UDP socket ... port 7777` + `Host is shutting down due to network transport
start failure`. The squatter can be the host editor's OWN leaked socket from a previous paired
run that died without a clean transport shutdown — `lsof -nP -iUDP:7777` names the PID; match
its `-projectPath` before touching anything. **A domain reload does NOT free the leaked socket**
(native allocation, no managed finalizer path) — restart exactly that editor process
(scheduled `EditorApplication.Exit(0)` via delayCall may never fire on an unfocused editor;
direct `Exit(0)` or SIGTERM to the verified PID works, then relaunch with
`open -na .../Unity.app --args -projectPath <checkout>`). Do NOT keep re-running the audit —
the second attempt fails identically and "back-to-back flake, re-run" is the WRONG diagnosis
for this signature.

## Divergence triage: check command TIMING first {#command-timing}

⚠️ **A mode-3 divergence is not automatically a SIM defect — check command TIMING first**
(feature 042, 2026-07-25). Before feature 042, `ffauto:heartbeats|N` advanced the sim one
heartbeat per rendered **frame** but chains awaited a **wall-clock** estimate; below ~10 fps the
next command fired mid-pump and phase-shifted otherwise identical fingerprint streams. Current
source registers the manual pump's `ChainCompletion`
(`LocalMultiplayerAutomationCommandRunner.cs:1017-1019`) and both chain executors claim and await
that completion before proceeding. The check remains useful for historical reports, unmerged
branches, and any future regression of that ordering.
🔑 **How to check**: the Editor.log interleaves `[DeterminismAudit][Heartbeat N]` lines with
`[determinism] setup '<cmd>'` lines, so scanning it while tracking the last-seen heartbeat gives
**the heartbeat each command actually fired at**. Compare that against the testcase's pump
schedule before hunting a simulation bug. Tell-tale signature: identical stream lengths, and the
same fingerprint sequence phase-shifted rather than genuinely different values.

## TestcaseFilter: targeted mode-3 investigation {#testcasefilter}

🔑 **`DeterminismTestRunner.TestcaseFilter`** (committed value `null` = whole corpus) restricts the
gate to one testcase — a targeted investigation costs ~3 minutes instead of the ~10-50 minute
sweep. A successful filtered investigation ends NUnit **Ignored**, not Passed, and is **not** a
gate result; a divergence still fails normally.

## Throttling the editor needs a holder {#fps-holder}

🔑 **Throttling the editor to reproduce a timing bug needs a HOLDER, not a one-shot**: the game
caps its own frame rate at boot (`DisplaySettingsController`, "Capping FPS on system start"), so
re-apply `QualitySettings.vSyncCount = 0` + `Application.targetFrameRate = <n>` every ~10 s for
the whole play session via `unity-cli eval_file`.

## Clone setup: FMOD symlink + wrong-dir traps {#clone-setup}

- ⚠️ **The clone needs a manual `FMODProject` symlink**
  (`ln -s ../<base>/FMODProject ../<base>_clone_0/FMODProject`) — ParrelSync only links
  `Assets`/`ProjectSettings`/`Packages`, but the FMOD banks live at the project root
  (`FMODStudioSettings.asset` `sourceBankPath: FMODProject/...`). Without it the clone's FMOD
  bank-load exceptions look non-fatal but **silently break the multiplayer save-apply**: the
  clone connects (`IsConnectedClient=True`) yet its world never materializes
  (`players=0, placeables=0`, stuck at `joining-localhost`). Headless build audits are
  unaffected (banks ship in StreamingAssets) — easy to misdiagnose as a join/netcode bug.
- ⚠️ **Multiple project copies exist side by side** (e.g. `FinalFactory`, `FinalFactory2`), each
  with its own `_clone_0` doing its own updates. A wrong-named dir is a **different project's**
  clone — never write triggers/configs there. Always derive the clone path from the current
  project folder name (`$(basename "$PWD")_clone_0`) and confirm the `Assets` symlink target
  before using it.
- On some Windows machines the clone's `Packages/` is a REAL directory, not a symlink — package
  pin bumps must be copied in and resolved on the clone explicitly (see project-memory
  `knn-profiling-and-fork-pin-gotchas`).

## Clone stale assembly: force the recompile {#clone-stale-assembly}

The ParrelSync clone runs its own `Library/ScriptAssemblies` and does NOT auto-recompile code
edits made after it booted. Before any paired run after a code change, force its recompile
**through the MCP bridge** — the clone is its own connected instance: find it in
`mcpforunity://instances` by its `path` (`…/<this project's folder name>_clone_0/Assets`),
`set_active_instance` to that `Name@hash`, call `refresh_unity` (or `run_tests` on it), then
`read_console` on the clone to confirm a clean compile (no `error CS`) before pinning back to
this project. (First run on stale code otherwise silently uses the old build.)

## Wrapper-script traps: dwell sizing, phase-1 timeout, detached launch {#wrapper-script-traps}

- 🔑 **The dwell is WALL-CLOCK but every acceptance bar counts SHARED HEARTBEATS** (feature 039,
  2026-07-24). Multiplayer only reaches 8 UPS if the peers keep up, so on a slow or loaded
  machine the same dwell yields far fewer heartbeats: the identical `MODE=place` window produced
  **234** shared heartbeats on one session and **102** on another *with no code change between
  them*. A short window makes an audit look like it passed when it merely did not run long
  enough to disagree. **Override `HOST_DWELL_MS` / `CLIENT_DWELL_MS`** to buy the heartbeats a
  criterion needs instead of quietly accepting a short run — e.g.
  `MODE=build HOST_DWELL_MS=100000 CLIENT_DWELL_MS=88000 ./run_construction_audit.sh` gave
  **323** shared heartbeats where the 60 s default gave 183. `CLIENT_DWELL_MS` must be **less
  than** `HOST_DWELL_MS` (hard-enforced, exit 2) so the host outlives the client and the shared
  window is not truncated.
- 🔑 **`timed out waiting for test-results.txt (editor closed / in play mode?)` in phase 1
  usually means NEITHER** (feature 039, 2026-07-24). Both editors are triggered CONCURRENTLY, so
  two full EditMode suites plus domain reload and test-framework init contend for the same
  cores. **Before believing the message, `cat <root>/test-results.txt` in both roots** — if it
  says `PASSED`, the suite simply finished after the script gave up, and you only need to
  re-run (the compile is warm the second time). The ceiling is `RECOMPILE_WAIT_TICKS`
  (240 ticks × 2 s = 480 s default), raised from a fixed 180 s that three consecutive runs
  overran on a loaded machine.
- **Launch long audits detached**: `nohup ./run_construction_audit.sh > log 2>&1 < /dev/null &
  disown`, and monitor the LOG FILE rather than the job — a tracked background task was reaped
  mid-phase-1 and reported as killed with no audit failure at all. (`setsid` does not exist on
  macOS.) Wait for BOTH editors to report ready + `playMode: stopped`
  (`scripts/unity-cli.sh command --project-path <abs> editor_status`) before launching the next
  audit; a preceding paired session takes time to wind down.

## Quarantined-testcase gate flake: the flip rule {#quarantine-flip-rule}

(Recipe retained from the pre-011 HaulerTwoStopLoop quarantine — that specific flake cannot
recur since 011's fp `HaulerFlightRails` made hauler flight deterministic and the quarantine was
removed, but the rule applies to any FUTURE quarantined testcase.) The mode-3 gate can report
FAILED while every active testcase PASSes when a testcase is quarantined `ExpectedDivergence`
WITHOUT `MayAgree:true` and its divergence is flaky — the flip rule (`DeterminismTestRunner.cs`,
T013) hard-fails an agreeing quarantined run-pair. Triage: grep the editor log for
`[determinism] (PASS|FAIL|QUARANTINED)` lines in that run's window. `MayAgree:true` is the
flaky-tolerant escape hatch.

## Cross-machine: proven runs + known limits {#cross-machine}

Proven 2026-07-11: M5 Pro 18-core vs M3 Pro 11-core, NO DIVERGENCE on movement (209 hb) + heavy
construction (461 hb, 12 lines/8 bots). Proven 2026-07-26 on Wittlebase: 681 shared heartbeats
from heartbeat 1 with zero authoritative divergence, while 668 raw float-heavy research
diagnostics differed and their normalized non-float state had zero differences
(`specs/038-join-desync-crafter-deploy/plan.md`, session handoff 2026-07-26k). ⚠ Known limits
(021 backlog): a run that dies abnormally can strand an editor in Play mode (reset it manually —
no remote-MCP reach); the rolling report window evicts early heartbeats on long busy runs
(shorten `DURATION_S` to keep a burst in-window). The `.110` checkout can fail to fetch over its
non-interactive SSH session; fast-forward it with the exact command in
`Documentation/Two-Machine-LAN-Dev-Pair.md:34-48` when the pre-flight hashes differ.
