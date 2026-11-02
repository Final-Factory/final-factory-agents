# Determinism-audit gotchas and triage recipes

Dated, hard-won findings. Each entry names the feature/date it came from; the recipes remain
load-bearing for future runs even where the original defect is fixed.

## TOC

- [Full-window rule: never diagnose from a partial window](#full-window-rule) (052)
- [Inventory hash roles: retain the raw field, gate the contracted surfaces](#inventory-hash-roles)
- [A built player pair is the proof instrument for presentation leaks](#built-pair-proof) (055 R25)
- ["Missing report(s)" is NOT a stuck editor](#missing-reports) (045)
- [`run_build_multiplayer_audit.sh` on Windows: `--graphics`, a fresh `--label` per attempt](#build-audit-windows) (perf pass C; a clean run poisons it too, and FlowControl:TooSlow, w2298)
- [Divergence triage: check command TIMING first](#command-timing) (042)
- [Every join forks within a few heartbeats: an upgrade step re-ran on the joiner](#join-upgrade-rerun) (w2767)
- [TestcaseFilter: targeted mode-3 investigation](#testcasefilter)
- [Throttling the editor needs a holder](#fps-holder)
- [Clone setup: FMOD symlink + wrong-dir traps](#clone-setup)
- [Clone stale assembly: force the recompile](#clone-stale-assembly)
- [Wrapper-script traps: dwell sizing, phase-1 timeout, detached launch](#wrapper-script-traps) (039)
- [Quarantined-testcase gate flake: the flip rule](#quarantine-flip-rule) (pre-011, recipe retained)
- [Cross-machine: proven runs + known limits](#cross-machine) (021/038/045)
- [Long-lived paired editor: restart between legs](#long-lived-editor)
- [Fresh-world proof does not cover old saves](#fresh-vs-old-saves)
- [Audit scripts must be Git-bash-portable (BEAST)](#git-bash-portable)
- [`run_enemy_audit.sh` never builds; macOS needs Homebrew bash](#enemy-audit-build-and-bash) (055 R29)
- [Wait for a running BEAST sweep before bundle-syncing](#beast-sweep-wait) (055)
- [Never run the two editors' fast suites concurrently](#no-concurrent-fast-suites)
- [Burst is OFF by design on paired automation runs](#burst-off-by-design) (editor host with a built-player client: Burst, enemy gen, FlatMap drops, w2306)
- [Built-player pair harness needs role-keyed identity, not per-copy keying](#built-pair-identity) (049 T028b)
- [Silent-weakening audit class: assert the leg your docstring claims to prove](#silent-weakening) (049 T028b)
- [Built-player sessions need an opt-in watcher to outlive a pair break](#outlive-pair-break) (049 T028)
- [Mute the real audio path — `-batchmode -nographics` does not touch FMOD](#automation-mute) (049)
- [Fixture determinism can be CPU-load-dependent even with no cross-peer comparison — unverified](#fixture-load-dependence) (055 R35)
- [Host-frame profiling: a probe, not a determinism gate](#perf-probe) (055 flag lane 3)
- [A big save: the full capture keeps the client out; the runtime detector and a capped host](#big-save-pair) (w780; bench stops and a too-heavy client, w2567)
- [Old against new in one pair: a PR's A/B switches on one peer](#ab-switch-one-peer) (w1115)
- [Reading a pair's witness-compare.txt: pose distance is the verdict](#witness-pose-distance) (w1555)
- [A world-generation pair: drive the host post-join, compare lists, keep the client yours](#worldgen-pair) (w2271; world objects from saves, ffnightly deletes local saves, w2386)
- [A live-driven built pair: reopen panels after a resync, overlap the report windows](#live-driven-pair) (w2238)
- [A Linux client leg on biscuit: build, headless launch, a scripted paste](#linux-client-leg) (w2133, w2326)
- [A Linux host leg on biscuit: console commands and detector counts from a headless host](#linux-host-leg) (w2281)
- [A host-only scenario with a remote client: pause on join, tower spawns, flow control](#host-scenario-remote-client) (w2586)
- [A hand-launched built host: TargetClients counts the host, and turn the audit on](#hand-launched-host) (w2797)
- [An ffnightly Linux host for a remote client: its port, its audit, its station builds](#ffnightly-linux-host) (w2824)
- [An editor pair with presentation checks: no Audit ids in the config, a healthy host, a client machine without bench rounds](#editor-pair-presentation) (w2399)
- [An Oracle shop pair: host buys first, `near` is tier 1, price is derived](#oracle-shop-pair) (w2518)
- [A mod pair with raw entity dumps: Comet Fragments spin differently on every peer; fuel and host-wait traps](#mod-dump-pair) (w2831)
- [A save-and-reload pair: checkpoints are rolling windows, the client rejoins by itself](#save-reload-pair) (w2558)

## Full-window rule: never diagnose from a partial window {#full-window-rule}

(This trap has burned the same lane twice.) The corpus comparator reports
only the FIRST divergence, which can hide the real defect: the 052 hauler triage confidently
claimed a divergence "exactly one heartbeat wide" that was actually e1 hb1 MISMATCH, hb2 MATCH,
hb3-12 MISMATCH with the client hash FROZEN — fixing only the first-heartbeat cause would have
moved the fork hb1→hb3 and left the testcase red. Second instance: "epoch 2 ran 260/260 clean →
recovery re-anchors correctly" was FALSE — the "clean" claim came from a partial-window diff,
and a re-diff found `combat` mismatches at e2 hb9-14. **Always extract and diff per-heartbeat
hashes from BOTH `*-report.log` files over the FULL window before believing any diagnosis** —
and remember an epoch window in which no ops actually fired proves nothing about the surface
("clean" windows are only evidence when the ops that could disagree actually ran).

**The same trap has a per-FIELD axis, not just per-heartbeat.** A top-line verdict like `differing fields: combined movers vision` or a bare
"PASS"/"NO DIVERGENCE" does not tell you whether OTHER fields on the same surface would also
disagree if you looked — R26 and R28 both closed their fix only after an **independent
per-field re-fold of every surface over every shared heartbeat** (not just the one the
comparator flagged) found zero mismatching fields elsewhere; R28's re-fold is what proved
`movers`/`vision`/`combined` were the ONLY three differing fields out of 23 surfaces, ruling out
a second live cause. A fix that only silences the field the comparator happened to print is
unproven — re-fold every field, not just the named one, before calling a fix complete.

**The text-mirror comparator can hand you a partial window without saying so** (w173, 2026-10-01).
`compare_determinism_reports.sh` reads the report's text mirror, which is a bounded tail of the
run. In a windowed two-peer session of about 3,500 heartbeats it printed `NO DIVERGENCE:
fingerprints match on all 2573 shared heartbeats (epoch 1 hb 917 .. 3489)`, and every op under
test had applied between heartbeats 375 and 641. `python scripts/audit/compare_audit_records.py
<host report> <client report>` reads the structured `audit-record-v1` records and compared all
3,489. For any session longer than about two and a half minutes, use the typed comparator, and
check that the first shared heartbeat it prints is before your ops.

## Inventory hash roles: retain the raw field, gate the contracted surfaces {#inventory-hash-roles}

`PlayerInventoryHash` folds the slot arrangement of every authoritative player inventory in one
peer's world. It is a same-peer diagnostic because remote-player inventory is an asynchronous
projection, so the raw hash is excluded from `Combined` and the wire surface set
(`Assets/Scripts/FFSystems/Multiplayer/DeterminismStateFingerprint.cs:62-80,291-323`). It is still
emitted beside every other fingerprint field
(`Assets/Scripts/FFSystems/Multiplayer/DeterminismFingerprintSystem.cs:144-170`). Keep it in captures
and report whether it changed; do not hide or delete the field to make a cross-peer run pass.

Adjudicate the mismatch from the source contract. Use a same-peer repeated run to gate the raw slot
hash. For op-driven cross-peer inventory scenarios, gate `PlayerInventoryTotalsHash`, which sorts
item totals independently of slot placement, plus every affected cross-peer field such as
`containers` and `combined` (`DeterminismStateFingerprint.cs:82-95`; the inventory audit applies
this split at `scripts/audit/run_inventory_audit.sh:216-235`). If a raw inventory mismatch appears,
state it and its same-peer-only verdict role explicitly; a comparator exemption is not permission
to suppress the evidence silently.

## A built player pair is the proof instrument for presentation leaks {#built-pair-proof}

The Step()-pumped editor pair advances at most one heartbeat per
`EditorApplication.Step()` call and therefore renders roughly one frame per heartbeat — it ran a
2114-heartbeat CombatLifecycle scenario with a live presentation→simulation leak (a rail mirror
reading a player's per-render-frame presentation velocity) and reported **NO DIVERGENCE**, because
the bug needs MANY render frames between heartbeats to manifest (the owning peer's local-input
write and a remote peer's NetworkVariable-smoothed write only diverge over real frame timing). A
fresh macOS standalone player pair built from the same tree, run through the identical scenario at
real frame rates with Burst ON, forked immediately and reproduced the exact production hashes.
**Any suspected controller-group/presentation-sourced field (`FleetCommanderSystem`-style leaks,
per-frame mirrors, anything reading a `LinearMotion`/transform field that a player writes from
input) is not cleared by an editor-pair NO DIVERGENCE** — build and run
`run_build_multiplayer_audit.sh` before trusting the surface, and treat a built-pair fork that an
editor pair cannot reproduce as confirmation of the presentation-leak class, not a flaky harness.

## "Missing report(s)" is NOT a stuck editor {#missing-reports}

A completed paired run and a genuinely stuck editor produce IDENTICAL script output, and
`ERROR: missing report(s)` after the full wait loop usually means report **discovery** failed
rather than the run. Every `run_*_audit.sh` discovers via `da_find_report`
(`determinism_audit_lib.sh`), which matches LABEL + the report's own `role=` header (filenames
lie: a `MODE=client` run's HOST report contains "client" in its name). **The diagnostic lesson
stands for any report-discovery failure: before concluding an audit run failed for environment
reasons, look in the `DeterminismAudit/` output dir for reports matching the label. If they
exist, the run succeeded — evaluate them directly (source `determinism_audit_lib.sh`, use
`da_find_report` / `da_assert_field_aligned`, which key off file CONTENT) instead of restarting
editors.**

## Missing reports on BOTH sides: check for a leaked UDP port first {#port-leak}

`ERROR: missing report(s) — host='none' client='none'` on a CLEAN start (phase-1 suites green on both editors) with the clone left stuck in play mode
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

## `run_build_multiplayer_audit.sh` on Windows: `--graphics`, a fresh `--label` per attempt {#build-audit-windows}

(BEAST ffsb sandbox, 2026-09-27, perf pass C.) Two ways the build-driven paired audit fails on Windows
without any divergence:

- **Headless players cannot render DOTS.** The default `-batchmode -nographics` players throw
  "Attempting to create a graphics buffer that requires compute shader support" every frame (a 42 MB
  host log), the client times out joining, and only one report is written (`missing report(s)`, exit 3).
  Pass `--graphics`.
- **A failed run poisons its label.** It leaves `network-determinism-audit-legacy-<label>-<role>.partial`
  in `LocalLow/.../DeterminismAudit`; the next run with the SAME `--label` fails publication with
  `Audit artifact identity collision` (exit 3, that role's report missing). Use a fresh `--label`.
  A run that went well poisons it too (w2298, 2026-10-26): a hand-launched pair-run client re-joined
  with the same `-ffAutomationLabel` after a first try was kicked, ran a clean 11,558-heartbeat window,
  and lost its report to the first try's `...-<label>-client.log`. So put the attempt in the label
  (`w2298-client-2`) on every launch. If it happens anyway, the player's `-logFile` holds every
  `[DeterminismAudit]` line: `grep -a 'DeterminismFingerprintSystem -> Fingerprint '` from it, under a
  `# determinism-audit-report` header line, gives a file `compare_determinism_reports.sh` reads.
- **A client the host kicks with `FlowControl:TooSlow`** (`PeerCatchUpTracker.JudgeDrop`, the
  not-converging rule: 5 s behind, under 0.5 s gained in 20 s) ran too slowly under the full audit's
  logging (w2298: about 6 heartbeats a second on a busy LothDesktop, kicked 22 s after joining). Relaunch
  the host with `-ffFlowControlWaitForSlowPeers` (`HeartbeatSystem.cs`, host only): it holds the
  heartbeat for the slow peer instead of dropping it, and the rerun caught up in 45 s and held 12.8 UPS.

Any dev player works: `FF_BUILD_DIR=<dir holding finalfactory.exe> ... --skip-build` (e.g. an
`Editor.ShaderBenchBuild` bench build), `--host-extra "-ffAutomationSave <name>"` runs it on a real save,
`--port N` avoids a busy one. A pass prints `NO DIVERGENCE` and `PASS [playerSimPos]`. The script starts
both players from a player slot (`FF_LAUNCH`, `scripts/nightly/player_launch.sh`), so a new build folder
raises no firewall prompt; start any player by hand the same way (`player_slots.py launch`). On a worker-root install (LothDesktop since w576) each sandbox slotK has its own two player folders, `players/slotK-0` and `slotK-1`: `launch` picks them from the sandbox it runs in, and `--peer 1` puts a same-build client in `slotK-1` (project-memory `feedback-built-players-run-from-the-slot-pool`).

The shared audit folder bites the fast suite too: `NetworkDeterminismAuditReportTest` fails with an
IOException (`...partial` "being used by another process") while any automation player writes there.
Re-run it with no players running.

## Divergence triage: check command TIMING first {#command-timing}

⚠️ **A mode-3 divergence is not automatically a SIM defect — check command TIMING first.** The
failure this guards against: a pump that advances the sim one heartbeat per rendered **frame**
while the chain awaits a **wall-clock** estimate, so below ~10 fps the next command fires
mid-pump and phase-shifts two otherwise identical fingerprint streams. Current source registers
the manual pump's `ChainCompletion`
(`LocalMultiplayerAutomationCommandRunner.cs:1017-1019`) and both chain executors claim and await
that completion before proceeding, so this should not recur — but check it anyway on reports from
an unmerged branch, and on any suspected regression of that ordering.
🔑 **How to check**: the Editor.log interleaves `[DeterminismAudit][Heartbeat N]` lines with
`[determinism] setup '<cmd>'` lines, so scanning it while tracking the last-seen heartbeat gives
**the heartbeat each command actually fired at**. Compare that against the testcase's pump
schedule before hunting a simulation bug. Tell-tale signature: identical stream lengths, and the
same fingerprint sequence phase-shifted rather than genuinely different values.

## Every join forks within a few heartbeats: an upgrade step re-ran on the joiner {#join-upgrade-rerun}

**Symptom** (w2767, 2026-11-01): every join of one save forked at the same early heartbeat (8), on one
fingerprint (containers), and the resync never cleared it (RecoveryFailed). The cause was one structure
type's slots off by one between host and client: on a Singularity Power Station, host
`[0:105x75, 4:105x7]` against client `[0:105x74, 4:105x8]`. A pending command in the host's live dump
(`JunctionChainDetail cmds=[...]`) looked like the cause and was not: `InventoryCommand` is not saved,
and the dump was taken mid-heartbeat.

**Cause**: an upgrade step versioned above the running build (`Step1_0_0_30PowerStationFuelSlots` on a
1.0.0.29 build) is still pending for the join snapshot that build writes, because `UpgradeChain.Applicable`
is strict on the version. With `PostLoadRunsOnRemoteSnapshot` true (it was the default), the joiner ran
the step again on the host's already upgraded world. A step that is not idempotent then forks the joiner
alone; a resync re-serves the same snapshot, the step runs again, and recovery fails every time.

**Check first**: grep both peers' Player.log for upgrade-step lines (`Upgrade Step`, a step's own log
prefix such as `[Step1_0_0_30PowerStationFuelSlots] Gave N`). A step line in the client's log after it
joins is the cause (here the client logged `Gave 30`, the host `Gave 159` at its own load).

**Fixed** in FinalFactory PR #2956: the default is now false, and `UpgradeStepRemoteSnapshotTest` fails
on any step that opts in to running on a join snapshot. Seeing this again means a step overrides it to
true, or a load path that skips `UpgradeChain.PostLoadSteps(..., isHost)`.

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

- 🔑 **The dwell is WALL-CLOCK but every acceptance bar counts SHARED HEARTBEATS.**
  Multiplayer only reaches 8 UPS if the peers keep up, so on a slow or loaded
  machine the same dwell yields far fewer heartbeats: the identical `MODE=place` window produced
  **234** shared heartbeats on one session and **102** on another *with no code change between
  them*. A short window makes an audit look like it passed when it merely did not run long
  enough to disagree. **Override `HOST_DWELL_MS` / `CLIENT_DWELL_MS`** to buy the heartbeats a
  criterion needs instead of quietly accepting a short run — e.g.
  `MODE=build HOST_DWELL_MS=100000 CLIENT_DWELL_MS=88000 ./scripts/audit/run_construction_audit.sh` gave
  **323** shared heartbeats where the 60 s default gave 183. `CLIENT_DWELL_MS` must be **less
  than** `HOST_DWELL_MS` (hard-enforced, exit 2) so the host outlives the client and the shared
  window is not truncated.
- 🔑 **`timed out waiting for test-results.txt (editor closed / in play mode?)` in phase 1
  usually means NEITHER.** Both editors are triggered CONCURRENTLY, so
  two full EditMode suites plus domain reload and test-framework init contend for the same
  cores. **Before believing the message, `cat <root>/test-results.txt` in both roots** — if it
  says `PASSED`, the suite simply finished after the script gave up, and you only need to
  re-run (the compile is warm the second time). The ceiling is `RECOMPILE_WAIT_TICKS`
  (240 ticks × 2 s = 480 s default), raised from a fixed 180 s that three consecutive runs
  overran on a loaded machine.
- **Run pair audits and recorded two-peer sessions with nothing else of yours running** (w154,
  2026-10-01). Gates that compare dumps scheduled by wall clock, or that need both peers to keep
  up, fail under load while the fingerprints still match. Two cases on one machine:
  `run_same_name_zone_audit.sh` failed its gate 4 ("both stations hold the zone at int3(0, 0, 0)":
  the client's dump ran one step ahead of the stations' pick) while two windowed players were
  running, and passed twice when run alone on the same build; and a recorded windowed two-peer
  session had its client dropped by the host (`FlowControl:TooSlow`,
  `peers=1:5.0:DroppedTooSlow`) while a batch build or a `watch_video` review was running. Before
  blaming your change for a kick, look for the same line in a session on a build without it. The
  typed comparator still covers the session up to the drop.
- **Launch long audits detached**: `nohup ./scripts/audit/run_construction_audit.sh > log 2>&1 < /dev/null &
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

## Long-lived paired editor: restart between legs {#long-lived-editor}

A paired-audit editor left running ~8 hours across many legs was observed at ~40 GB heap, and at
that size it timed out the audit's own fast-test gate (the suite simply never finished within
the wait budget). Restart both editors between legs on a long audit session rather than reusing
one across the whole day — don't spend time diagnosing a "flaky" fast-test gate before checking
the editor's own memory footprint.

## Fresh-world proof does not cover old saves {#fresh-vs-old-saves}

A paired proof run on a FRESH world only exercises the fresh-world code path. Any change that
touches a LOAD path (save format, load-time migration, a component that gets populated
differently on load vs on create) needs a SEPARATE old-save fixture arm in the same audit —
"NO DIVERGENCE on a fresh world" says nothing about whether an existing save still loads and
stays in sync.

## Audit scripts must be Git-bash-portable (BEAST) {#git-bash-portable}

Several audit scripts already carry macOS-only tool calls (`shasum`, `stat -f`) that fail under
Git Bash on the Windows BEAST box, which needs `sha256sum`/`stat -c` instead. Before adding or
sweeping audit scripts, grep new/changed ones for mac-only tool names and add the portable
fallback (`command -v sha256sum >/dev/null && sha256sum ... || shasum ...`, same pattern for
`stat`) rather than discovering the break on the Windows machine.

## `run_enemy_audit.sh` never builds; macOS needs Homebrew bash {#enemy-audit-build-and-bash}

`scripts/audit/run_enemy_audit.sh:99` (`run_player_pair`) always
calls `run_build_multiplayer_audit.sh` with `--skip-build` — this script never builds a player
itself, and exits 2 (preflight failure) if none exists. Build one first:
`run_build_multiplayer_audit.sh --label <x>` (editor CLOSED, `Temp/UnityLockfile` removed if the
editor was killed rather than quit), THEN run the enemy arm against it. A `--skip-build` reuse of
a build that has already hosted one paired session fails its own manifest sha256 check (the
session mutates the `.app`) — a build can be reused for a SECOND arm, a third needs a fresh build.

`scripts/audit/run_determinism_testcases.sh` does not parse under macOS's system `/bin/bash` 3.2
(`line 435: syntax error near unexpected token 'str'`) — install a modern bash (`brew install
bash`) and invoke explicitly: `PATH="/opt/homebrew/bin:$PATH" /opt/homebrew/bin/bash
./scripts/audit/run_determinism_testcases.sh …`. Distinct from the BEAST Git-bash-portability
trap above (that one is about Windows Git Bash lacking GNU tool variants); this one is macOS
shipping an 18-years-stale bash by default.

Its own `--skip-build` is a SEPARATE flag from `run_build_multiplayer_audit.sh`'s above, with its
own manifest: `validate_build_manifest()` (`run_determinism_testcases.sh:339-347`) fails loudly
(`ERROR: --skip-build requires a build manifest at $BUILD_MANIFEST`) unless a prior run of THIS
script already wrote one. Run it WITHOUT `--skip-build` first so it builds and records its own
manifest; only pass `--skip-build` on a later reuse against the same artifact.

## Wait for a running BEAST sweep before bundle-syncing {#beast-sweep-wait}

(055, `specs/055-combat-mover-vision/plan.md:200-203`.) BEAST runs sweeps of paired arms as a
standing background job; a leg that syncs a new build/bundle onto the box, or launches its own
paired run, while a sweep is still in progress races that sweep's own build/state. Check
`beast-sweep-status.ps1` reports **Ready** before bundle-syncing or starting a new arm there —
it is a machine-local script on the BEAST box itself, not checked into this repo.

## Never run the two editors' fast suites concurrently {#no-concurrent-fast-suites}

(062 fix, e.g. `scripts/audit/run_construction_audit.sh:123-128` and the same pattern repeated
across every `run_*_audit.sh`.) The host and clone editors' fast EditMode suites share the
`DeterminismAudit` write path — running them concurrently corrupts each other's output. Every
paired-recompile call now goes through `determinism_audit_lib.sh`'s `da_recompile_editor_pair`,
which runs the two suites SEQUENTIALLY, not concurrently. Don't hand-roll a parallel recompile
of both editors to save time — that's the exact regression 062 fixed.

## Burst is OFF by design on paired automation runs {#burst-off-by-design}

`LocalMultiplayerAutomationLauncher` deliberately disables
`BurstCompiler.Options.EnableBurstCompilation`/`EnableBurstCompileSynchronously` for every local
automation editor session just before entering play mode, and logs `[LocalMultiplayerAutomation]
Disabled Burst compilation for this local automation editor session.`
(`Documentation/Unity-MCP-Setup.md:163-168`, `Documentation/Runtime-Desync-Detection.md:158-163`).
This is symmetric across both peers and editor-local only — production/standalone AOT Burst
settings are untouched. Seeing Burst come up OFF right as a paired automation run starts is
expected, not a probe failure or something to "fix". This is separate from
`editor-preflight.sh`'s check, which validates the PERSISTENT editor setting is enabled before
automation starts (catching a stale prior-session disable) — the automation launcher's own
runtime disable happens afterward and is intentional.

**An editor host with a built-player client (w2306, 2026-10-26, m5 macOS editor host, LothDesktop Windows player):**

- The handshake refuses the Burst player: "Jobs mismatch: host jobs=managed, client jobs=burst"
  (`FFCore/Network/PeerCompatibilityToken.cs:286`, from `BurstSelfCheck.JobsRunManaged`). The launcher turned Burst off
  (`Behaviours/Multiplayer/Editor/LocalMultiplayerAutomationLauncher.cs:266,289`). Before entering play mode, in one
  `execute_code` call set `BurstCompiler.Options.EnableBurstCompilation` and `EnableBurstCompileSynchronously` to true and
  reset `BurstSelfCheck._described` to null by reflection (`FFCore/Network/BurstSelfCheck.cs:31,36`: the cache keeps
  "jobs=managed option=off" from an earlier play session). Confirm the log line `[Burst] self-check: jobs=burst option=on`.
- `DisableEnemyGeneration` is per peer: the host's `.ff-local-automation.json` does not reach the client
  (`LocalMultiplayerAutomationBootstrap.cs:1797-1799`). Pass the player `-ffAutomationDisableEnemyGen true` (`:75`,
  applied on join at `:1032`). Without it a generated map desynced at the first fast flight into new chunks
  (asteroids, camps, movers, census; host camps hash empty `88201FB960FF6465`, client nonzero), recovery re-diverged
  twice and the client was kicked. Camps diverging while enemies are "off" means this.
- `lagprobe.drops` ResearchDrops can never be collected on a FlatMap: `PickupableVacuumSystem.cs:329` returns early with
  "Failed to get biome id for research drop". A drop or vacuum check needs a generated map (`FlatMap` false).

## Cross-machine: proven runs + known limits {#cross-machine}

Proven on M5 Pro 18-core vs M3 Pro 11-core: NO DIVERGENCE on movement (209 hb) + heavy
construction (461 hb, 12 lines/8 bots). Proven on Wittlebase: 681 shared heartbeats
from heartbeat 1 with zero authoritative divergence, while 668 raw float-heavy research
diagnostics differed and their normalized non-float state had zero differences
(`specs/038-join-desync-crafter-deploy/plan.md`, session handoff). ⚠ Known limits
(021 backlog): a run that dies abnormally can strand an editor in Play mode (reset it manually —
no remote-MCP reach); the rolling report window evicts early heartbeats on long busy runs
(shorten `DURATION_S` to keep a burst in-window). The `.110` checkout can fail to fetch over its
non-interactive SSH session; fast-forward it with the exact command in
`Documentation/Two-Machine-LAN-Dev-Pair.md:34-48` when the pre-flight hashes differ.

**Cross-machine earlygame legs**, four traps: (1) the M3 editor launched over SSH
had Burst DISABLED (the one-way automation-launcher switch, see
[Burst is OFF by design](#burst-off-by-design) — this was the PERSISTENT setting, not the
per-session runtime disable) and the 045 preflight fails closed on it — re-enable via
`scripts/unity-cli.sh command --project-path <repo> eval_file file=<cs>` running
`Unity.Burst.BurstCompiler.Options.EnableBurstCompilation = true;`, then the preflight reports
"Burst queue is still compiling" for a few minutes — a retry loop on the audit script itself
(90s cadence) is the simplest drain wait. (2) With `HOST_IP` auto-detected as the LAN address
the client's UnityTransport got "Failed to connect" / `MaxConnectionAttempts` although raw UDP
(`nc`) between the same hosts worked and the host bound `0.0.0.0:7777` — an SSH-launched Unity
editor on a fresh Unity build is subject to macOS Local Network privacy and nobody clicked its
prompt. `HOST_IP=<host Tailscale IP>` (100.x, the documented off-LAN override) joined first
time; traffic to a 100.x address is not gated by that permission. (3) The verification capture
cap `MaxVerificationSamples` was 4096 (`NetworkDeterminismAudit.cs`); a 240s opening+combat leg
needs 6-8k host samples (the host's solo window while the client loads the transfer counts) —
raised to 16384 (`b06d210bb`). (4) `verification-overflow` / `artifact-unreadable` verdicts
carry `forkEvents` in `verdict.json` context: an empty list on an overflowed run still means the
captured window compared clean.

## Built-player pair harness needs role-keyed identity, not per-copy keying {#built-pair-identity}

A built-player pair audit runs TWO PROCESSES OF ONE BUILD on
ONE MACHINE — every per-editor-copy trick that keeps an editor pair's host and client apart
(ParrelSync's separate `Assets`, a project-path-keyed identity file) does nothing here, because
there is only one binary and one set of on-disk singletons. Two premise breaks surfaced this way:
(1) both processes shared ONE Steam login via `GameStateRpcManager` — fixed by
`SteamworksManager.ShouldInitializeSteam(enableSteamworks, automationRole)`
(`Assets/Scripts/Steam/SteamworksManager.cs:44-46`), which skips Steam init whenever an automation
role is set, giving every automation peer `steamId 0`; (2) both processes read/wrote ONE
`reclaim-identity.txt` via `ClientReclaimIdentity.GetStorePath` — the editor/ParrelSync trap already
had per-copy keying, but no built-player counterpart, fixed by
`ClientReclaimIdentity.ComputeStoreFileName` (`Assets/Scripts/PlayerController/ClientReclaimIdentity.cs:77-92`)
falling back to `reclaim-identity-automation-<role>.txt` when there is no editor project key.
**Rule**: a built-player pair harness must role-key every singleton a single build would otherwise
let two processes share — audit for MORE than the one that just broke, since editor-copy keying does
not generalize to a single shared binary.

## Silent-weakening audit class: assert the leg your docstring claims to prove {#silent-weakening}

(049 T028b, `22a8c8ca4`.) Before the identity fix above, `run_player_persistence_audit.sh`'s
`MODE=rejoin` arm (`scripts/audit/run_player_persistence_audit.sh:38-52`) documented itself as
proving GUID reclaim — a departed player's Guid re-parked and reclaimed on rejoin — but the shared
`reclaim-identity.txt` meant the arm was silently passing through the SteamId-keyed reclaim leg
instead, per the fix commit's own message. `AutomationLanIdentityTest.AutomationSessionsDoNotLogIntoSteam`
(`Assets/Tests/Playtest/AutomationLanIdentityTest.cs:48-55`) now asserts the automation precondition
(`steamId==0`) the arm depends on, in-run. **Rule**: an audit arm whose preconditions are documented
only in a docstring — never asserted in the run itself — can prove a WEAKER claim than advertised
while still reporting PASS; sweep arms for unasserted preconditions, not just for wrong assertions.

## Built-player sessions need an opt-in watcher to outlive a pair break {#outlive-pair-break}

(049 T028, `5c0550919`.) Evict/leave/rejoin/saveload arms deliberately break the pair mid-session —
one peer disconnects, then reconnects. Without `-ffAutomationOutlivePairBreak`
(`Assets/Scripts/Behaviours/Multiplayer/LocalMultiplayerAutomationBootstrap.cs:1991`), the session
watcher's default `ShouldEndSession` policy (`LocalMultiplayerAutomationBootstrap.cs:912-929`) tears
the session down the moment the pair breaks, before the pending rejoin chain ever completes. Pass the
flag for any arm whose chain SPANS a disconnect/reconnect; leave it off for arms that don't, since it
changes when the session is allowed to end.

## Mute the real audio path — `-batchmode -nographics` does not touch FMOD {#automation-mute}

(049, `cb5bd8cab`.) Built automation players still make sound: `-batchmode -nographics` mutes
RENDERING, but Final Factory's audio runs through FMOD middleware, independent of Unity's
`AudioListener`/render pipeline — `AudioListener.volume = 0` alone does nothing. The fix mutes the
real path: `AudioController.SetAutomationMuted(true)` (`Assets/Scripts/Audio/AudioController.cs:51-55`)
calls FMOD's `RuntimeManager.MuteAllEvents` (`AudioController.cs:73`), called from every automation
role's `LocalMultiplayerAutomationBootstrap.ApplyGlobalSettings`
(`Assets/Scripts/Behaviours/Multiplayer/LocalMultiplayerAutomationBootstrap.cs:412`) alongside a
belt-and-braces `AudioListener` kill. **Rule**: automated runs must stay silent while Ben is at the
machine — any new automated-run entry point (built player OR editor) needs to call the FMOD mute
path, not just the Unity one.

## Fixture determinism can be CPU-load-dependent even with no cross-peer comparison — unverified {#fixture-load-dependence}

(055 R35 leg observation, unverified class.) Two identical single-fixture `MODE=economy` runs (no
second peer, so this is not a cross-peer desync) differed run-to-run on `movers` on a loaded machine,
while the same runs on a quiet machine reproduced exactly. This is an observation, not a confirmed
root cause — but it means a behavioral-fixture diff measured on a busy machine can look like a
regression that isn't one. **Diagnose fixture run-to-run drift on a quiet machine before treating it
as a code regression.**

## Host-frame profiling: a probe, not a determinism gate {#perf-probe}

`scripts/audit/run_perf_probe.sh` runs a real host+client built
pair and samples the HOST for N seconds with `ffauto:perf.sample|<seconds>|<topN>` (PerfProbe:
every top-level PlayerLoop stage, every FF system group via `FFSystemGroupSampler`, heartbeats
applied, GC allocated/frame, FrameTiming CPU times; presentation-only, zero cost when disarmed).
It emits one `PerfSample` critical record per second and one `PerfSummary` (ups, fps, avg/p95/max
frame ms, top stages + groups with % shares) and prints them as tables. `MODE=camps` loads the
enemy-economy fixture — the real-map arm the ~9 UPS finding came from. Run it on a QUIET machine
(a concurrent sweep skews it), reusing a sweep build via `FF_BUILD_DIR`; on BEAST the SYSTEM
account's `/tmp` is `C:/Windows/Temp`. This is a probe, not a gate — it is deliberately not in the
audit manifest.

## A big save: the full capture keeps the client out; the runtime detector and a capped host {#big-save-pair}

w780, 2026-10-09, °Life°'s Build 91 save (177,779 entities, 577 haulers), m5, built Mac players.

- **The full-capture paired audit cannot get a client in.** `run_build_multiplayer_audit.sh` with
  `-ffAutomationSave` on this save: with capture on, the host took about 10 s per heartbeat (single
  `HaulersDetail`/`Fingerprint` lines up to 900 KB), so it logged `Pending Client-1 connection approved!`
  only after the client's `Timed out waiting for the server to approve the connection request` and
  `ClosedByRemote`. Twice, the second time with `FF_CLIENT_LAUNCH_DELAY_SECONDS=30` (the w257 knob):
  the delay helps a slow first heartbeat, not a host that stays slow. Exit 3, `missing report(s)`.
- **What worked instead:** the same built players as a host + client pair on the save with
  `-ffAutomationDeterminismAudit false`, the client started 30 s after `host-ready`. The runtime desync
  detector compares every 8th heartbeat in any multiplayer session (`RuntimeDesyncDetection.SampleIntervalHeartbeats`)
  and logs only on a fork (`[DesyncDetector] Multiplayer desync detected`); count the shared heartbeats from the
  client's `[MP pacing] ... applied=` lines. Silence is the verdict only with those counts beside it. Say in the PR
  that this is the detector, not the per-surface audit (pr_evidence.py wants the heartbeat count on the
  `Determinism audit:` line).
- **`-ffBench` overrides the slow-host cap.** `ContentShaderBench` sets `Application.targetFrameRate = -1` every
  frame while it records (attach and save modes), so `-ffFeelProbe -ffFeelFps 20 -ffFeelVsync 0` on a bench host
  ran it at 62 fps. Run the 20 fps host without `-ffBench`, with `-ffAutomationPostConnectDelayMs` for the dwell, and
  read its `[MP pacing] frames=` (about 185 per 10 s at 18.5 fps) before calling it a slow-host leg.
- Both peers outlive their dwell with the audit off (the publish step fails: `The determinism audit is disabled`);
  stop them yourself at the end of the window.
- **w2400, 2026-10-27 (an ffnightly host-only scenario, a remote client by address, m5 host + loaded LothDesktop client):**
  - Read the detector's counts straight from the host: `ffauto:desync.stats` answers `compared`, `matched`,
    `diverged`, `firstHeartbeat`, `lastHeartbeat` per client. updatedLifeSave, audit off: 722 compared, 722 matched,
    heartbeats 8..5776, in 6 minutes of play.
  - **A host-only scenario passes with no client in it.** Run 3 ended `pass` after the client was kicked
    (`FlowControl:TooSlow`) and nothing had been compared. End the scenario with a `poll ffauto:desync.stats`
    on `data.clients[0].compared` `atLeast` (heartbeats / 8, less a margin), so a dropped client fails it.
  - The per-heartbeat audit (`-ffAutomationDeterminismAudit true`) on updatedLifeSave hung the m5 host 10 s at a time in
    `DeterminismFingerprintSystem.RecordDetail`; on JustPlay1003 it hung the client 13.5 s and got it dropped. On
    Wittlebase it ran, but a 4-worker client still fell behind after 200 heartbeats. Use the detector on those saves.
  - JustPlay1003 with the audit off: a client on a LothDesktop already at 63% CPU from other sandboxes was kicked
    `FlowControl:TooSlow` at `-ffJobWorkers 4` and at 8 (it never drained the ~450-heartbeat backlog after the world
    serve). Pick a lighter save or a quiet client machine before blaming the change.
  - Turn the presentation monitors off on a big save (`invariantsOff` as BAL-end-justplay): run 2 ended on the
    `transform` invariant (a Dyson Bot drawn 4,013 u from its simulation position), not a desync.
  - Second attempt (m5 host, BEAST client at `-ffJobWorkers 4`, 4dda4f981d): give `ffnightly.py run` a `--budget-min`
    above the scenario's `timeLimitS` in minutes. `--budget-min 120` with `timeLimitS` 7200 ended at once, `not-run`,
    `cut-off: budget` (`ffnightly.py` `over_time`, the `finish(... "cut-off: budget")` call); 200 ran it.
  - **A reconnect restarts the count.** The client rejoins as a new clientId in a new epoch, and `desync.stats` then
    counts only that epoch's compares. Client 1 was dropped `FlowControl:HardDrift` near epoch-1 heartbeat 3,500 (a
    12.1 s `[HangWatchdog]` hang in `NtCreateFile` on a BEAST running another player and three editors); the rejoin
    compared 420 of 420 over epoch-2 heartbeats 8..3360, and the scenario's `atLeast: 450` bar failed that clean pass.
    Size the end bar to one epoch's heartbeats / 8, and report which epoch the count came from.
- **w2567, 2026-10-29 (m5 headless host, BEAST windowed client, PR #2822's rotator change):**
  - Just Play 1.0.0.22 (468,003 entities, ~141k rotators) is too heavy for a windowed client with graphics on: the
    BEAST client applied 74 then 125 heartbeats per 10 s (one per frame, p50 53-60 ms) against 160, its backlog grew
    570 -> 611, and the host kicked it `FlowControl:TooSlow` a minute after the join. The golden fixture
    `LifeAsTwoMegaWave-0.50.0.54` (5,932 entities, 29 Mass Drivers, Singularity and Dyson rotators; the client spawns
    looking at a row of Mass Drivers) held 16 UPS at ~59 fps and passed 289 of 289 compares over heartbeats 8..2312.
  - **A client player on a shared big computer is stopped by other workers' exclusive bench tickets** (w1829), and the
    run is void. Two of w2567's runs died that way, one a minute after it started: it had slipped into a gap in which
    an exclusive ticket was already warned. Before you launch, read `bench_queue.py status` and the tail of
    `<worker root>/tmp/bench.queue/log.txt`: launch when a shared group runs with enough minutes before its deadline
    (`granted ... joins the running shared group with N min left before its deadline`), not just after a `warned ...
    its turn ends at` line. Don't gate on "no exclusive waiting" either: normal-priority exclusives can wait behind a
    shared group for its whole hour (`kept ... only lower-priority work waits`), and such a gate never opens.
- **w2578, 2026-10-29 (m5 host, BEAST headless client, PR #2829's shield change): run the host with
  `-ffFlowControlWaitForSlowPeers` on Just Play 1.0.0.22.**
  - A headless BEAST client (`-batchmode -nographics`) could not follow either: at 15 job workers and again at
    `-ffJobWorkers 31` it applied 37-96 heartbeats per 10 s (frameMs p50 70-110) against a ~900-heartbeat backlog left
    by a 136 s world serve, and was kicked `FlowControl:TooSlow`, with BEAST otherwise idle.
  - The host restarted with `-ffFlowControlWaitForSlowPeers` (`HeartbeatSystem.cs:161`, the 018 rule: the host holds
    production for its slowest peer) ran lockstep at the client's pace (~11 UPS): 1602 of 1602 compares over heartbeats
    608..13416. Report the real rate beside the count.
  - One client was evicted `FlowControl:HardDrift` by an 18.8 s main-thread hang in Backtrace's breadcrumb storage
    (`BacktraceStorageLogManager.ClearOldLogs` -> `BreadcrumbFile.GetIOStream`, a FileStream open in `NtCreateFile`)
    while it logged ~82k `Internal: deleting an allocation that is older than its permitted lifetime of 4 frames` lines
    in 3 minutes; likely the same `NtCreateFile` hang as w2400's. Not a desync: relaunch the client.
  - `player_slots.py launch` refuses at once (exit 2) while an exclusive bench ticket holds the lock: pass
    `--bench-wait 900` so the launch waits for it instead.
- **w2587, 2026-10-30 (BEAST host + LothDesktop client, Just Play 1.0.0.22, shields under fire):**
  - **The host waits 900 s for its clients, and only that** (`HostPeerConnectTimeoutSeconds = 900`,
    `LocalMultiplayerAutomationBootstrap.cs:146`). A client queued behind its own machine's bench lock misses it, and the
    host writes `session-ended: host-peers-never-connected` and quits. Run the host in a relaunch loop that stops on
    `status host-peers-connected`. Do not match `host-peers-connected:`, which also matches the
    `waiting-host-peers-connected:` line.
  - **A stopped wrapper leaves its launcher queued.** If you stop the bash around `player_slots.py launch --bench-wait`,
    its python launcher still waits for the bench lock and starts a second client later. The result is a double join
    (`connectedClients=3`), a void run, and a client-only `duplicate reservation keys in one named batch` exception from
    `CombatIdentityAssignmentSystem.cs:117` that the clean single join never showed. Run `ff-leftovers end` before
    relaunching a client.
  - **To get shield hits on Just Play 1.0.0.22**, whose 109 camps all sit outside the activity gate (`enemy.pressure`
    showed `inGate=0` and 134 shields stayed full), run `ffauto:enemy.frontier` on the host before the client joins.
    At heartbeat 2 it answers `not moved` because the signal footprint is still empty. A few hundred heartbeats later it
    moves the player, and 13 camps came into the gate.
  - **`shield.state`'s `absorbed=` covers only the last heartbeat.** Sample every second or so and look for `charge`
    below capacity: 508 samples over 8 minutes caught one grid at 14372/14400, recharging. Samples every 30 s missed
    every hit.

## Old against new in one pair: a PR's A/B switches on one peer {#ab-switch-one-peer}

w1115, 2026-10-12, nightly regression check of the Deck perf PRs (#1449, #1458, #1491), BEAST, built Windows players.

- **One paired run compares the old code path with the new one.** Perf PRs leave A/B switches that each process
  reads from its own command line (`Environment.GetCommandLineArgs`): `-ffLegacyKnnSort`, `-ffLegacySerialSettle`,
  `-ffLegacySerialRailSeed`, `-ffLegacyRailProvisioningSync`, `-ffLegacyDeathSync`, `-ffLegacyCometSync`,
  `-ffLegacyProjectileBirthSync`, `-ffLegacyVacuum`, `-ffLegacyLtWToggle`, `-ffLegacyInterpolationOverwrite`
  (grep `"-ffLegacy` for the current list). Put them on ONE peer (`--host-extra` on
  `run_build_multiplayer_audit.sh`, or `ffnightly.py run --peer-arg host=<flag>`) and the full fingerprint comparison
  is an equivalence check of the two paths: w1115's host on every switch at 19.9 fps against a client on the new paths
  matched on 1833 heartbeats. Check which surfaces moved (distinct values per field) before calling it a pass: on the
  enemy economy fixture `power` and `grids` never changed, so the settlement switch needed the battery scenario.
- **A nightly scenario without the audit has no per-heartbeat fingerprints.** Scenarios whose `peerArgs` do not set
  `-ffAutomationDeterminismAudit true` (most; `MP-W998-aggro-splash-join` does) leave the runtime detector as the only
  verdict, and `compare_determinism_reports.sh` answers `No fingerprint lines found`. Add
  `--peer-arg host=-ffAutomationDeterminismAudit --peer-arg host=true --peer-arg a=-ffAutomationDeterminismAudit
  --peer-arg a=true`; the players' own logs (`<out>/<scenario>-try1/host.log`, `a.log`) then compare directly.
- **Measure the slow peer, do not assume it.** `-ffFeelProbe` writes `feel_probe_<pid>.csv` in the game's data root
  (header line has the full command line; `t0` in ns, `hb` the heartbeat): frames over the steady window give fps and
  UPS. On a loaded BEAST a `-ffFeelFps 60` peer reached 23 fps and a 20 fps host 12.7 fps at 11.7 UPS; report the
  measured numbers.
- **Port 7777 is usually taken on a shared PC.** Another sandbox's audit holds it and the driver refuses to start.
  `FF_PAIR_PORT=<free port>` sets the driver's default for every wrapper that passes no `--port` (w1121, PR #1548). For
  `ffnightly.py`, copy `scripts/nightly/lab.win.json` into `$TMPDIR` with its own `port`, `workRoot` under `$TMPDIR`,
  `jobs: 1` and `runIn: sandbox`, and pass it as `--lab`. A sandbox has two player slots (`slotK-0`, `slotK-1`): run
  pairs one after another, and a three-peer scenario does not fit.
- **`--lab scripts/nightly/lab.win.json` runs both peers on one PC** (w1739, 2026-10-22): host and client in the
  sandbox's two slots over loopback. It counts as the two-player check when the brief allows any route, but write
  "same-PC pair, not two machines" under Not verified; a check that must cross hardware (core counts, job scheduling)
  needs a lab file naming two machines or the dispatcher's placement.

## Reading a pair's witness-compare.txt: pose distance is the verdict {#witness-pose-distance}

w1555, 2026-10-20. A Burst-off host against a Burst client shows 1-ULP differences on every heartbeat ("10296 of 10296
shared heartbeats have a different state hash"), with a fix and without one. The per-field rows list the first
difference of each field. Some of those fields are no longer read by the simulation, such as a rail-owned mover's
float `LinearMotion` velocity and disabled flag, so a row there is not a fork. The drift verdict for poses is the
growth table's `max pose distance` after heartbeat 1. With the S1 fixed-point movers it held at 0.0044 units over
10,296 heartbeats; on master one pose was 19 units apart by heartbeat 709. Heartbeat 1's large distance on the
player's own ship is the host's pose before the ship is placed: leave it out. Quote the windows and the largest
distance per run, alongside the runtime detector's verdict.

## A Linux client leg on biscuit: build, headless launch, a scripted paste {#linux-client-leg}

w2133 (2026-10-25, the client of a LothDesktop-host pair for PR #2507) lost about 40 minutes to four traps:

- **Build:** `scripts/nightly/build_player.sh` takes only `mac|win`. On Linux run
  `FF_BUILD_DIR=$TMPDIR/<leg>/player FF_LOG_DIR=$TMPDIR/<leg>/logs bash scripts/audit/run_build_multiplayer_audit.sh --build-only`
  (it takes its own Unity slot; one session with `-buildTarget StandaloneLinux64`).
- **biscuit has 26 GB:** with another sandbox's editor and player up, the kernel OOM-killed the build's Unity during
  Burst AOT (`journalctl -k`: "Out of memory: Killed process ... (Unity)"; the build log ends "BeeDriver connection
  terminated" in GenerateNativePluginsForAssemblies). It leaves an orphan `bcl.exe +burstc` (7 GB; `ff-leftovers end`)
  and a stale `Temp/UnityLockfile`, which makes the retry refuse at once as "the project is open in the editor". Check
  that `lsof` shows no holder, move the lock file into `$TMPDIR`, then build again; the retry went ok.
- **Launch headless:** a windowed player (`-screen-fullscreen 0`) quit twice on the fixed 30 s title-menu wait
  (`LocalMultiplayerAutomationBootstrap.cs` `EnsureTitleMenuReadyAsync`, `timeoutMs = 30000`) while it uploaded
  shaders to the GPU at ~1 s per variant. `-batchmode -nographics` joined at once.
- **Pasting a copy from a headless client:** `movement.goto` and `camera.zoom` onto the area first (without them the
  pointer projects off-screen), then `blueprint.copy|x1|z1|x2|z2`, `pointer.moveto|x|z`, `pointer.click`, and only a
  few heartbeats later `blueprint.drop`: a drop in the same chain as the click cancels the paste. `blueprint.ghosts`
  lists the IN-HAND blueprint's ghosts, not placed structures; `circuit.dump|x|z` at the tile shows a placed copy.
- `desync.stats` is host-only ("only the host compares fingerprints"); the client's evidence is its Player.log and
  `~/.config/unity3d/Never Games/finalfactory/desyncReports`.
- A timed run's exclusive bench ticket stops the client player mid-run (5-minute warning). Tell the host, keep the
  event under test (here: deconstructing B) until you rejoin, and relaunch once `bench_queue.py status` shows no
  exclusive holder.
- **End the client the moment the host says it ended or quit** (w2326, 2026-10-26). A client launched with
  `-ffAutomationRole Client` keeps its reconnect loop after the host goes (`[Reconnect] ReconnectAttempt(1..4)`,
  backoff 4-8 s, about 40 s in all), so it joins the host's NEXT run on the same address and port before that run's
  setup: twice in w2326 the LothDesktop host's restarted scenario then failed (`player.setposition` is refused once
  a client is in; "2 peers are already connected"). Run `ff-leftovers end` on the host's word, and launch a fresh
  client only on its "HOST WAITING".
  - Don't wait for the host's word (w2432, 2026-10-28): watch the client's log and end it at the first
    `ClosedByRemote`. In w2432 run 2 it rejoined the host's relaunched session within seconds, and the client's
    summed `[MP pacing] applied=` then counted two epochs as one run.
  - But end it at its log's `status report-written` line, a second or so after `status session-ended`, not at the
    first `WatchdogTripped` or `Disconnect Event` line (w2512, 2026-10-29): run 3 killed the client the moment the
    watchdog tripped, before `session-ended`, and it never wrote its fingerprint report; run 1 waited for
    `session-ended` and got it. Loop: `until grep -q 'report-written\|session-ended' "$LOG"; ...`, then a few seconds.
- **Sending ffauto commands to a Linux client** (w2558, 2026-10-29): `scripts/agent/peer.py` is Windows-only
  (PowerShell, `AppData`). On Linux, `player_slots.py launch --detach` prints `agent_session`, a
  `~/.config/unity3d/Never Games/finalfactory/AgentControl/session-<pid>.json` holding `port` and `token`; POST
  `http://127.0.0.1:<port>/v1/command` `{"actor":"local-player","command":"ffauto:..."}` with `Authorization: Bearer
  <token>`, retry on `rate_limited`, then poll `GET /v1/chain/<chainId>` until it leaves accepted/queued/running.
  `setting.shipyardpull` and `audit.write|<label>` worked that way from a `-batchmode -nographics` client.
  - **Launch it with BOTH `-ffAgentControl true -ffAgentControlDev true`** (w2838, 2026-11-01). `-ffAgentControlDev`
    alone sets only the tier: `AgentChannelHost.ResolveEnabled` reads only `-ffAgentControl`
    (`AgentChannelHost.cs:168-175`), so no channel opens. `launch --detach` still prints an `agent_session` path, but
    the file never appears. w2838's client found out mid-run and relaunched twice, so the first two epochs had no
    client report. Check that the session file exists right after the launch, before you send the host "joined".
- **A killed host relaunched on a save gets the same client back** (w2558): a client with
  `-ffAutomationOutlivePairBreak true` whose host was killed (so no `report-written`) and relaunched on the same
  address and port rejoined by itself in the same process and log (`ReconnectAttempt(2)` approved,
  `PlayerJoinedAlreadyApplied`, epoch 1 heartbeat 0). The host can keep it as run 2, but the client then writes no
  run-1 report: take `ffauto:audit.write|<label>` checkpoints on both peers at each step so every step has a pair.
- **Cancel a queued client launch with `ff-leftovers end`, never by stopping its shell task** (w2570, 2026-10-29). A
  `player_slots.py launch --bench-wait` started from a background bash task waits in a python process of its own:
  TaskStop on the bash leaves it waiting, and it starts the client the moment the bench lock frees. In w2570 the
  host had told the LothDesktop client to hold; the stray client joined the host's fresh run at heartbeat 8, before
  setup (the host refuses `blueprint.place` once a client is in), and the host had to start over. Run `ff-leftovers end`,
  then `ff-leftovers list` to check that no launcher or player is left. A LothDesktop client also loses its turn to
  every exclusive timed run there: that day three in a row cut or blocked it, so offer the host a machine with no
  timed runs early.
- **A host leg cannot wait out a client's outage; set its world up before any client can reach it** (w2570,
  2026-10-29). A fresh built host quits when no client joins within 900 s (`HostPeerConnectTimeoutSeconds`,
  `LocalMultiplayerAutomationBootstrap.cs:146`), and `-ffAutomationOutlivePairBreak true` keeps it only 300 s after a
  client drops (`PairBreakOutliveCeilingSeconds`, `:212`). So a host started before its client is ready, or
  one whose client is cut, ends by itself: launch it on the client's "ready", not before. Its setup through the agent
  channel (`blueprint.place`, `player.setposition`) is refused once any client is in ("must run BEFORE clients join
  (host PreConnectCommand)"). So either pass the setup in `-ffAutomationPreConnectCommandFile <file>` (`;`-chained
  `ffauto:` lines; it runs before `WaitForHostPeersConnectedAsync`, `:722-729`), or start each relaunched host on a new
  port that no earlier client is still retrying, set it up, then send GO with that port.
- **Where a structure's ships are:** `fleet.stationships` is a count of structure-owned ships with no location, and
  `fleet.dumpstate|wardens` lists only players' fleets, so neither shows a ship AT a given structure (w2512: the yard to
  Defense Platform flight was proven only by the host's `fleettransfer.take` from the platform).
  - `ff-leftovers end` ends EVERYTHING your session started, your own background `build_player.sh` too: in w2432
    the watcher's `ff-leftovers end` killed the control build running beside it (`build-failed`, entityFiles 0).
    While a build runs, end the client by its pid (the `pid` that `player_slots.py launch --detach` printed).
- **A pair-run dwell needs both caps raised** (w2432): `-ffAutomationPostConnectDelayHeartbeats N` alone still ends
  the dwell at `-ffAutomationPostConnectDelayMs`, 1500 ms by default (`dwell-started: durationMs=...` in the log
  shows it). A host with only the heartbeat cap quit after 24 shared heartbeats; give both peers e.g.
  `-ffAutomationPostConnectDelayHeartbeats 6000 -ffAutomationPostConnectDelayMs 720000`.
- **`flowcontrol.throttle` does not survive a desync recovery**: the recovery cancelled the chain holding it
  (`"status": "cancelled"`), and the client ran uncapped (~90 fps against the asked 60) for the rest of the run.
  Read the frame rate from `[MP pacing]` `frames=` per 10 s window, and re-issue the throttle after every epoch change.
- **An editor client leg against a remote host** (w2399, 2026-10-27, biscuit editor joining an m5 editor host over
  Tailscale with `.ff-local-automation.json` `Role` `Client`, `Host` the host's address):
  - **Read biscuit's bench queue before you start the session**: `~/ffw/tmp/bench.queue/log.txt`. A line `warned
    ... running editor slotN ... its turn ends at HH:MMZ` means an exclusive timed round closes your editor within
    5 minutes, play mode and session lost. w2399's session 1 was cut at 13:34Z before its capped flight, and its next
    turn at 13:45Z was a 4-minute window. A line `granted ... running editor slotN: it joins the running shared group
    with N min left before its deadline` is a usable window: session 3 ran its whole step list in a 58-minute one.
  - **The bootstrap writes `AutoStartInEditor: false` into the config once it consumes it**
    (`LocalMultiplayerAutomationBootstrap.cs` `sessionConfig.AutoStartInEditor = false`). A copy saved after the
    first session never enters play mode again until you set it back to `true`.
  - **Let a host that just loaded a save settle about 20-25 s before the client joins.** In w2399 session 2 the host
    sent heartbeats 1-4 and then stalled for about 5 s after the load: the client logged `[MP pacing] ... maxGapMs=3960
    rttMs=6191`, then `[Reconnect] WatchdogTripped appliedAgeSeconds=5.0`, and shut down (the host saw
    `ClosedByRemote`); its reconnect attempts then timed out. Session 3 waited 25 s after the load and held.
  - The UnityMCP server can fail to connect for a whole session; `scripts/unity-bridge.py eval` / `eval_file`
    drives the same editor (state reads, `ffauto:` commands through `LocalMultiplayerAutomationCommandRunner.TryExecute`,
    an `EditorApplication.update` per-heartbeat sampler installed after play mode starts, since entering play mode
    reloads the domain and drops it).
- **A built client leg run several times: a fresh label per run, end it at `report-written`** (w2658, 2026-10-31, a
  BEAST Windows client of an m3 host, PR #2898, three runs on ports 7931-7933):
  - A client without `-ffAutomationAutoQuit` stays up after `status report-written`, and its reconnect loop keeps
    retrying the host's address. Run 1's client was still up 4 minutes later. End it yourself: wait for that line,
    then a few seconds, then kill its pid.
  - A run with the same `-ffAutomationLabel` as an earlier run in the same data folder loses its final report:
    `status report-error: System.IO.IOException: Audit artifact identity collision at
    ...network-determinism-audit-legacy-<label>-client.partial`. Host and client both lost run 3's final report this
    way. Give every run a fresh `-ffAutomationLabel`, and fresh `audit.write` labels too (`<label>-r3-<HHMM>`).
  - `ffauto:audit.write|<label>-<HHMM>` checkpoints on both peers at every whole UTC minute saved the comparison:
    the merged checkpoints compared 3938 shared heartbeats. Start the loop from the client's `status dwell-started`.
  - `player_slots.py launch --detach` prints a `player slot ...` line before its JSON, so parse only the last line.
  - Give a Windows client its own `-logFile "$TMPDIR/<leg>/client.log"` (w2724, 2026-11-01, a BEAST client of an m5
    host). Without it the player writes the shared `AppData/LocalLow/Never Games/finalfactory/Player.log`, and other
    sandboxes' players on BEAST (SoloAutomation runs) started and overwrote it twice within 10 minutes: the client's
    join, dwell and `report-written` lines were gone, and an until-loop on `report-written` matched another player's
    log. The live state was still readable with `python scripts/agent/peer.py <label> get client v1/snapshot/session`
    (heartbeat, epoch).
  - Checkpoints plus Player.log were about 1.3 GB raw. A zip of them was 268 MB, over publish_attachment's 200 MB;
    `XZ_OPT="-6 -T0" tar -cJf` made 7.5 MB.
  - **A client with the host's heartbeat target loses its final report when the host quits first** (w2763,
    2026-11-01, a BEAST client of an m5 host, PR #2950). Both peers ran `-ffAutomationPostConnectDelayHeartbeats 12000`
    with `-ffAutomationAutoQuit true -ffAutomationOutlivePairBreak true`. The host reached 12000 first, wrote its report
    and quit at 05:54:26Z; the client, at its heartbeat 11439, logged `ClosedByRemote`, fell to the menu and never
    wrote `session-ended` or `report-written`. The minute checkpoints saved the run: the next `audit.write` (05:55,
    sent from the menu) still held fingerprints 0..11439, the whole run. Give the client a lower heartbeat target than
    the host (or have the host wait for the client's `report-written` before it quits), and keep the checkpoint loop
    going one minute past the host's quit.
  - **A Mac host for a desync pair runs headless, with `transform` off too** (w2793, 2026-11-01, an ffnightly host-only
    scenario on m5 with a LothDesktop client, PR #2981):
    - With `"windowed": true` the host hung at `waiting-title-menu` while the Mac's display slept. The HangWatchdog
      report put the main thread in `GfxDeviceMetal::WaitForLastPresentationAndGetTimestamp`. Drop `windowed`.
    - The headless host's `transform` presentation invariant ended a small FlatMap new game after about 1,500
      heartbeats, not only a big save. The player was drawn 7.81 u from its simulation position at 0 u/s, against a
      6 u bound. The client was dropped (`ClosedByRemote`). Put `"transform"` beside `"ups"` in `invariantsOff`.
    - `compare_audit_records.py` prints `hit its sample cap` whenever a VerificationOverflow record exists. With
      `omitted=0` nothing was dropped, so read `omitted` before you call the window short.
    - The client's Player.log `[DeterminismAudit][Heartbeat N][Epoch E][client] DeterminismFingerprintSystem ->
      Fingerprint ... details=` lines, paired with the host's `host.log` on (epoch, heartbeat), cover the tail past the
      last checkpoint. Typed checkpoints compared 13,291 heartbeats and the text lines 13,344.

## A Linux host leg on biscuit: console commands and detector counts from a headless host {#linux-host-leg}

w2281 (2026-10-26, the host of a biscuit-host, LothDesktop-client pair for PR #2534) ran the host `-batchmode
-nographics` from the slot pool, and four things settled what took the time:

- **Console commands before the join** go in the launch:
  `-ffAutomationPreConnectCommand 'ffauto:console.run|learnTech "Railguns";ffauto:console.run|forceAttack 12;ffauto:wait|30'`
  (`;` separates commands, `wait|<seconds>`). `console.run` works headless, and `forceAttack`/`learnTech` are not
  refused on a listening host before a client joins (its log shows `[QuantumConsole] > forceAttack 12` and the next
  `[EnemyRaid]` line).
- **Sample counts from a headless host:** nobody can type `desync.stats` there, so chain it after the join:
  `-ffAutomationPostReadyCommand 'ffauto:wait|120;ffauto:desync.stats;ffauto:wait|120;ffauto:desync.stats;...'`. Each
  result is a log line `Executed post-ready-command 'ffauto:desync.stats' => {..."compared":N,"matched":N,"diverged":0,
  "firstHeartbeat":8,"lastHeartbeat":H...}`. The detector compares one heartbeat in 8 (measured: 3,596 samples over
  heartbeats 8..28,768), so 3,500 samples take about 28,000 heartbeats, about 29 minutes at 16 UPS.
- **Lab fixtures** (`lab:w1440-lifesave-0.50.0.105.zip` and the other `lab:` saves) are only in LothDesktop's nightly
  `fixtures/` folder; biscuit has none. Ask the other leg to `publish_attachment` it and `fetch_attachment` it here.
- **A build waits out another sandbox's timed run:** `run_build_multiplayer_audit.sh --build-only` gave up twice with no
  build log while slot3's exclusive bench ticket held biscuit. Loop on `bench_queue.py status` until no exclusive
  holder shows, then build (the third try built in about 6 minutes). A bench warning that your player's ticket ends did
  not stop the running host that time, but the client leg had already quit on it: restart both fresh.

## An ffnightly Linux host for a remote client: its port, its audit, its station builds {#ffnightly-linux-host}

w2824 (2026-11-02, biscuit Linux host and a BEAST Windows client for PR #3002, circuit-module power) ran a host-only
scenario through `ffnightly_linux.py run --lab <copy of lab.linux.json with its own port>`. It took six host launches
to get two good runs. These were the causes:

- **The host listens on the lab's port + 1.** With lab ports 7951 and 7953, the host listened on 7952 and 7954. Check
  with `ss -uanp | grep "pid=<host pid>,"` before you post HOST WAITING.
- **ffnightly turns the audit off** (`automation_args`: `-ffAutomationWriteReport false`, no
  `-ffAutomationDeterminismAudit`). Then `audit.write` checkpoints are refused. Give the scenario
  `"peerArgs": {"host": ["-ffAutomationDeterminismAudit", "true", "-ffFlowControlWaitForSlowPeers"]}`. Then
  concatenate the host's `Checkpoints/*/...-<label>.log` files and the client's minute checkpoints, and compare them
  with `compare_audit_records.py`. It keys on (epoch, heartbeat), so concatenated files merge. Here it compared 5602
  heartbeats. `compare_determinism_reports.sh host.log client.log` covered the tail, 6304 heartbeats.
- **Every rerun gets new `audit.write` labels**, not only a new client label. A rerun with the same host label
  collides (w2658), so build the label from a run id (`w2824-host-r2-<step>`).
- **A poll's `path` is resolved against the command's result.** `circuit.dump` has `name` at its top level, so
  `data.name` works. On `observe.state|structure` the path `data.item` stayed None for 600 s, although the result
  held `data.item` = "Cargo Hold". Poll with `circuit.dump`, or read the commands.jsonl line before you trust a path.
- **A second Station Core 15 tiles away (25,10) stayed a frame** (`activeTask AddStation`) for 8 minutes, with the
  player at its spawn and two construction bots. The cause was not proven. At 19,10, after
  `movement.goto|<midpoint world x>|<world z>` between the stations, it was built within 50 s. Before you set a
  circuit on a structure, poll `circuit.dump|x|z` `data.moduleOnStation` for it.
- **`transfer.put` answers "requested ... via heartbeat queue" even when the host refuses it.** Run 1 never filled
  its hold: the player had no Iron Ore left after `craft.queue|Construction Bot|2` (the cause is a guess), and every
  transfer was refused. The refusal shows only in host.log: `[InventoryTransfer] Refused ... NothingInSource`. Grep for
  it after the first cycle. Move an item that the setup does not spend (`inventory.add|Connector|60`), and record the
  hold's `observe.state` inventory beside each `circuit.dump`.
- Step overhead: each `do` step costs wall time. 8 put/grab cycles with 4 dumps each took 4.7 min, not the planned
  2 min, so the host ran about 7 hb/s of wall time. Size the client's `PostConnectDelayHeartbeats` from heartbeats.
  Run 1's ~5550 heartbeats ran in ~13 minutes.

## A hand-launched built host: TargetClients counts the host, and turn the audit on {#hand-launched-host}

w2797 (2026-11-01, an m5 Mac host of a BEAST Windows client, PR #2989) launched its host with `player_slots.py launch`
(not ffnightly) and lost one run to each of these:

- **`-ffAutomationTargetClients` counts the host itself.** The default, 2, means the host plus one client
  (`LocalMultiplayerAutomationBootstrap.cs` `connected >= _options.TargetClientCount`; the host's own connection makes
  `connectedClients=1`). With `-ffAutomationTargetClients 1` the host logged `host-peers-connected: connectedClients=1`
  and began its dwell at once, before any client joined. Leave the flag out, or pass 2 for one client.
- **The host needs `-ffAutomationDeterminismAudit true -ffAutomationWriteReport true`** as well as the client. Without
  them the host ran the whole dwell and then ended `report-error: The determinism audit is disabled.`, and refused
  every `audit.write` checkpoint ("the audit is disabled").
- Post HOST WAITING only after the log shows `waiting-host-peers-connected: connectedClients=1,target=2` following the
  last `pre-connect-command-complete`. Run 3, with both flags fixed, compared 2000 shared heartbeats.

## A host-only scenario with a remote client: pause on join, tower spawns, flow control {#host-scenario-remote-client}

w2586 (2026-10-29: biscuit host, LothDesktop client, PR #2838 for w2575, an unpowered Construction Tower sends no
bots). The host ran `ffnightly_linux.py` with a host-only scenario that waits for the remote client. Ten runs found
the following:

- **The host pauses while a client syncs in.** Run8 sent a command just after `desync.stats` first listed the client,
  and got `state_not_playable: commands need a running game; the game is 'paused'`. The scenario failed, the host
  quit, and the client lost the connection with ClosedByRemote. Poll `desync.stats` on path
  `data.clients[0].compared`, atLeast 16, before the next command. A `heartbeats` wait does not cover the pause.
- **`spawn.ships|<bot>|N|towers` drops silently for an unpowered tower.**
  - Cause: `ExecuteShipSpawnCommandSystem.cs:2328-2334` rejects a tower at satisfaction <= 0 (`Unpowered`), and
    `:1291` drops the command for good.
  - Run9 ran with 0 tower bots: `fleet.stationships` count was 0, and every task was pending with "no free
    construction bot". The PR looked broken in phase 2 and was not.
  - For an unpowered-tower setup, power the tower for a moment. Place a panel, poll satisfaction >= 0.1, spawn the
    bots, and poll `fleet.stationships` `data.count` >= N. Then remove the panel and poll the battery's `charge` <= 0.
    Do all of this before the join.
- **`flowcontrol.throttle|60|<s>` does not cap a built player's frame rate.** On the LothDesktop Windows client it
  logged as applied, but measured about 200 fps headless and 143 to 240 fps windowed. Report the fps you measured.
- **Tailscale path churn drops a client.** The client's rtt went from 29 to 280 ms as its path moved between the DERP
  relay and a direct route. The host then dropped it with `FlowControl:TooSlow` (rule=not-converging, behind 5.0 s)
  at hb 392, and once before at hb 2672. With `-ffFlowControlWaitForSlowPeers` in the lab host peer's `"args"`, the
  pair held for 3,742 heartbeats.
- **Units, chains and ports:**
  - `movement.goto` takes world units, 10 per tile. `construction.placeitem`, `transfer.put` and
    `observe.state|structure|x|z` take tiles.
  - One `do` chain holds at most 64 segments, so split long ghost rows.
  - A multi-command evidence `do` keeps only the last result, so use one command per evidence step.
  - The client's reconnect loop rejoins a relaunched host on the same port, so give every relaunch a new lab port.

## A live-driven built pair: reopen panels after a resync, overlap the report windows {#live-driven-pair}

w2238 (2026-10-26, PR #2585's speed-cap slider, LothDesktop client against a BEAST host, driven with `peer.py ... cmd
client "ffauto:..."`):

- **A forced resync (any world reload) closes the client's UI panels.** The client's scheduled
  `ffauto:ui.set|fleet|...|100` came back `panel 'fleet' is not open` and the cap change was lost until it was resent.
  Send `ffauto:ui.open|<panel>` right before every `ui.set`; it is idempotent (`panel 'fleet' already open (no-op)`).
- **A report holds only the last ~3000 heartbeats** (`NetworkDeterminismAudit.cs` `MaxRecentEvents`, as the host leg
  read it). Run 1's host wrote its report 5 minutes after the client's, so the two reports shared only 314 heartbeats,
  short of the 1000 the brief asked for. Have both peers write within a minute of each other: matching
  `PostConnectDelayMs` end times, or `ffauto:audit.write|<label>` checkpoints at the same UTC times on both.
- **A client on a loaded machine can be dropped as too slow.** In run 2, LothDesktop was running 7 editors and two
  other players. The client went from InStep to `CatchingUp` 14 s after a mid-run checkpoint write (17 MB), drifted to
  5.1 s behind, and the host dropped it at heartbeat 3189 with `FlowControl:TooSlow` (`AutoQuit` then ended it). The
  final report it wrote on the kick still counted: with the host's checkpoints it gave 2299 shared heartbeats. Read
  `FlowControlDiag` in the client's Player.log for the drift; on a busy machine keep the shared run short.
- `scripts/nightly/reach.py` is missing at PR heads older than w2259: run master's copy with
  `git show origin/master:scripts/nightly/reach.py > "$TMPDIR/reach.py"`.

## A world-generation pair: drive the host post-join, compare lists, keep the client yours {#worldgen-pair}

w2271 (2026-10-26, the gas giant fix of PR #2604 for w2260) checked that both peers generate the same world objects while
the host flies rings of 400 to 1600 tiles. What it took:

- **`player.setposition` is refused once a client has joined** (`EnsureHostBeforeClientsJoin` in
  `LocalMultiplayerAutomationCommandRunner.cs`). Fly with `ffauto:movement.goto|<worldX>|<worldZ>|tolerance=150|timeoutSeconds=300`
  (world = tile x 10; measured about 10 tiles/s) and poll `GET /v1/snapshot/player` (`data.position.tile`) until the
  player is within ~20 tiles. A fixed sleep per point cuts corners on the outer rings: a 1600-tile ring's chord takes
  ~150 s. Chunks generate on both peers from the host's replicated simulation position.
- **While a goto chain runs, every other `/v1/command` answers `"status":"accepted"`** with an empty result and queues
  behind it. Read the answer at `GET /v1/chain/<chainId>`; don't treat "accepted" as success.
- **`desync.stats` cannot prove the lists match.** Its census surface folds entity counts per archetype
  (`DeterminismStateFingerprintJobs.cs`, the census hash at ~5148); it has no ItemIdentifier, and a world object's
  GridTile is in no surface. Compare per-object lists on both peers: `ffauto:worldobjects.list|84,207` (item@x,y,z sorted,
  count per id, FNV-1a hash), on branch `w2271-pair-instrument` (commit adb0ea0b) of the game repo, not yet on master.
  Read each peer after the host parks, before it moves on.
- **A client leg run by another worker can vanish mid-run.** w2271's client leg was moved to another machine three
  times (LothDesktop 09:14Z, biscuit ~09:45Z, LothLaptop ~11:04Z), and each move left a client nobody could read. When the
  check does not need two different machines, the host leg runs the client itself in its sandbox's second slot:
  `player_slots.py launch --detach --peer 1 ... -ffAutomationRole Client -ffAutomationHost 127.0.0.1`, then reads both
  peers. That pair flew all four rings (400 to 1600 tiles) in 55 minutes with lists equal after every ring.
- **The `desyncReports` folder under LocalLow is shared by every sandbox on the machine.** Before claiming a report,
  grep its `.player.log` for the slot path (`slot5-0` and so on) and match it to your own players.
- A worker's `$TMPDIR` can be swept while it waits for a pair partner (twice in w2271, builds included). The slot pool
  still holds the player: copy `players/slotK-N/player` back into `$TMPDIR/builds/<sha>-win/player` and launch that,
  since `player_slots.py` refuses a path inside the pool.
- **Comparing world objects from saves, on master builds** (w2386, 2026-10-27; m5 Mac host with a BEAST Windows client
  through `ffnightly.py run`). `worldobjects.list` above is only on a branch. Instead, save on every peer at one heartbeat
  (`ffauto:game.save|<name>_{peer}|atheartbeat={hb+80}` plus the `saveFingerprintsMatch` assert) and parse each save.
  Its `AllEntitiesColumnar_Part*.dat` parts (magic `FFC1`, layout as in the game repo's `scripts/save_census.py`) hold a
  68-byte `FFComponents.Core.Placeable` column. Each generated object has PlayerPlaced = 0 at byte 0. ItemIdentifier is
  an int32 at byte 20. GridTile is int3 x,y,z at 48 (y is height). Direction is an int32 at 64. The
  `Unity.Transforms.LocalTransform` rotation is bytes 16..32 of its 32-byte column. Map item ids to names through the
  IdToNameMap in `SaveState2.dat`: an int32 count, then (int32 id, 7-bit-length string) pairs. Sort the lines
  `name|x,y,z|d<dir>|<rotation hex>` per ring and hash them. Objects whose archetype holds RotationParameters (the
  Comet Fragments) spin, so leave their rotation out. Seed 2381 gave 170/539/1383/2714 objects at 400/800/1200/1600
  tiles, identical on both peers.
- **ffnightly deletes the local peers' saves when the scenario ends.** `unstage_save` (`scripts/nightly/ffnightly.py`,
  ~783) removes the names the scenario's `game.save` steps wrote from this machine's `UserData/saves`. A remote-win
  peer's saves stay in `C:/Users/<user>/AppData/LocalLow/Never Games/finalfactory/UserData/saves`, for `scp`. Copy the
  local ones out while the run goes: start a background loop that copies `UserData/saves/<name>*.zip` into `$TMPDIR`
  once each file's size has held steady for 5 s.
- **Size "N minutes after the join" in heartbeats at 16 UPS, not from goto timeouts.** `movement.goto` with
  `devunlock` flies about 250 u/s and finishes well inside its timeout (1,700 tiles in ~70 s). So w2386's first run
  ended 12.5 minutes after the join instead of 15. Its final hold of 6,400 heartbeats became 10,400.

## An editor pair with presentation checks: no Audit ids in the config, a healthy host, a client machine without bench rounds {#editor-pair-presentation}

w2399 (2026-10-27) was a two-editor pair: an m5 host and a biscuit client checking the speed cap (#2585). Besides the
fingerprints, it sampled the remote ship's presented `LocalTransform` every host frame to count snaps.

- **Leave `AuditRunId`, `AuditLegId` and `AuditSourceRevision` out of `.ff-local-automation.json`.**
  - The trap: setting them without a full audit save identity makes the editor bootstrap refuse the config with
    `audit-config-invalid … Audit save identity is required`, so play mode never starts.
  - Without them the run writes the legacy report, `DeterminismAudit/network-determinism-audit-legacy-<label>-<role>.log`.
    It holds typed `# audit-record-v1` Fingerprint records, and you compare them per heartbeat and epoch.
  - To start a new session, set a new `Label` and set `AutoStartInEditor` to true again. The bootstrap resets it to
    false after each start.
- **A snap count (jumps over `RemotePlayerPresentation`'s SnapThreshold of 25 u) means something only on a healthy
  host.**
  - Read the host's `[MP pacing]` lines for the flight window before judging snaps.
  - The healthy session: the host applied 160 of 160 heartbeats per 10 s, with frames well under 100 ms. Uncapped
    flight gave 0 snaps and a max per-frame jump of 2.46 u.
  - The overloaded session: other game players were running on m5, at a load average of about 7.5. The host applied
    130–158 of 160 heartbeats per 10 s, with frames up to 1.47 s. That gave 2–3 snaps of 26–31 u per 10 s flight,
    capped and uncapped alike.
  - Name the host load in the verdict, or rerun on an idle host.
- **On a slow host, judge speed by `SimulationVelocity` and the per-heartbeat median, not by distance ÷ heartbeats.**
  - The client's own ship moves in wall time and its position rides each heartbeat. With fewer heartbeats arriving,
    each heartbeat carries more distance.
  - The overloaded session measured 67.6 u/s at a cap of 60, about 160 ÷ 142 × 60.
- **Put the client leg on a machine with no exclusive bench rounds.**
  - On biscuit the bench queue closed the client editor mid-run for another request's exclusive timed run.
  - Its shared turns between rounds were only about 5 minutes.
- **A 5 s heartbeat gap right after the host loads a save trips the client's reconnect watchdog.**
  - The client logged `[Reconnect] WatchdogTripped appliedAgeSeconds=5.0`, and the host logged `ClosedByRemote`.
  - Let the host settle for about 20 s after it starts listening before the client joins.

## An Oracle shop pair: host buys first, `near` is tier 1, price is derived {#oracle-shop-pair}

w2518 (2026-10-29) was a built-player pair run for w2510 (game PR #2792): a BEAST host and a LothDesktop client at
commit 66dcc01. It checked that each Oracle reveal costs 3 more orbs and stays in sync across peers.

- **`-ffAutomationTargetClients` counts the host itself.**
  - With `1`, the host started its dwell at once (`host-peers-connected: connectedClients=1`). The client joined a
    game that was already running.
  - `-ffAutomationInvulnerablePlayers true` then covered only the host (`players-invulnerable-authored: players=1`).
  - Use `2` for one client. Run 2 logged `players=2,target=2`.
- **`player.setposition` works only on the host before the join.** The runner's help line says "host PRE-join only".
  - Put the host's teleport in `-ffAutomationPreConnectCommand "ffauto:player.setposition|x|z"`.
  - Fly the client with `ffauto:movement.goto|<tileX*10>|<tileZ*10>|tolerance=100|timeoutSeconds=300`.
- **A client that flies to a hidden Oracle uncovers it by fog.**
  - A later host "Reveal Nearest Oracle" was refused `NoHiddenOracle` (run 1, hb 11589).
  - Keep the client still until the host's buy lands.
- **`oracle.buy|<label>|1|near` means tier 1: the first tier-1 Oracle, not the one the player stands at.**
  - The client's buy at 65:-294 named -79:98 and was refused `SoldHere`.
  - Use `tier2` or `far` for the tier-2 Oracle.
- **The buy needs no activation.**
  - `OracleTransactionClientRequest` checks only that the player can pay, that a hidden Oracle exists, and the tile.
  - `mining.startnearestactivation|80|oracle` never logged `[Activation] landed` in 2 to 7 minutes in these built
    players. The cause was not checked.
  - On the client, range 80 found nothing at 69:-294. Range 200 did, at distance 105.
- **No ffauto command prints the reveal price. Derive it.**
  - Read `sold=` from `oracle.list`; the price is 3 x (sold + 1) (`OracleRevealItem.CurrentCost`).
  - `oracle.state` gives each player's orbs. Each player's balance took both players' `AddLumenOrbs 50`, so both
    showed 100. After the 3-orb buy the host had 97 and the client 100.
- **Write checkpoints at one agreed UTC second on both peers** (`ffauto:audit.write|<label>-cp1`).
  - This gave 2541 shared heartbeats with no divergence, in a run whose dwell still had 15 minutes left.

## A save-and-reload pair: checkpoints are rolling windows, the client rejoins by itself {#save-reload-pair}

From w2558 (2026-10-29), a built-player pair of the Ship Yard "Take ships from assemblers" switch (PR #2821): host on beast
(Windows), client on biscuit (Linux), with a save and reload on the host.

- **`ffauto:audit.write|<label>` writes a rolling window of about 2,400 heartbeats, not the whole run.**
  - w2558's step checkpoints each compared 1,607 to 2,547 shared heartbeats.
  - For the full-window verdict, run `scripts/audit/compare_determinism_reports.sh <host.log> <client Player.log>` on
    the two players' whole logs. It reads their `[DeterminismAudit]` Fingerprint lines. w2558: run 1 compared 8,121
    heartbeats (hb 1..8121), run 2 compared 5,194, and none diverged.
  - When one client process served two host runs, split its log at the first `ReconnectAttempt` line. Both runs use
    epoch 1, so their heartbeat numbers collide.
- **A save-and-reload on the host needs no client relaunch.**
  - Save with `ffauto:game.save|ffa-<session>-<name>` and end the host (`ff-leftovers end`). Relaunch it with
    `-ffAutomationSave ffa-<session>-<name> -ffAutomationFlatMap false`.
  - A client still in its dwell (AutoQuit plus a long `-ffAutomationPostConnectDelayMs`) rejoins the reloaded host by
    itself: `ReconnectAttempt(1)` times out, attempt 2 is approved, then `RejoinWorldApplied` and `ReconnectRestored`
    at epoch 1, hb 2.
  - This proves the rejoin path, not a fresh-launch join. Say so in the report. A killed host writes no
    `report-written` line, so neither peer gets a final report: take an `audit.write` on both peers before the kill.
  - There is no ffauto quit command (`session.stop` only ends a playtest session).
- **Powering a Ship Yard in a FlatMap test** (yard at origin (17,-5) facing Up, 12x7, center (20,0)):
  - The working chain is a Solar Panel (Direct) at (13,0) rotated with `rotate.abs|13|0|1`, which put it at (12,1).
  - Then a Ship Assembler at (14,0), then a Strut at (16,0) facing 1 (Right), on whitelisted yard slot 21 (left side).
  - A Strut at (16,-5) (slot 0) or one facing Up left the yard unpowered.
  - Read the yard roster from the `FleetsDetail` fingerprint lines: `consumer=(20,0,0) fleet=N/60 ... ships[N]=[...]`,
    where 134 is a Miner Bot and 24 a Bat.
  - A held finished ship shows as the assembler's `craftProgress` above 1 with recipe set (`observe.state|nearby|x|z|r`).
- **Frames more than about 20 tiles from the player never build.**
  - The player's actionRange is 200 world units, 10 per tile.
  - A frame out of range stays `frame` with "no free construction bot". Move with `movement.goto|<x*10>|<z*10>|tolerance=10`
    first.

## A mod pair with raw entity dumps: Comet Fragments spin differently on every peer; fuel and host-wait traps {#mod-dump-pair}

w2831 (2026-11-01, for w2827) checked Gherik's FinalFactoryMods20 mods (HybridFuelConsumers, AsteroidTow, Batnado) on a
BEAST host and a LothDesktop client. It used a read-only test mod that writes the mods' components to a text dump every
80 heartbeats on each peer, and diffed the dumps beside the fingerprint reports.

- **Comet Fragment rotation differs on every peer; it is the base game's, not a mod's.**
  - Comet Fragment roots (ItemIdentifier 41, PlaceableType MinableTerrain) had different `LocalTransform.Rotation`
    float bits on host and client in every dump block of all three scenarios. Their positions and tiles matched.
  - They spin in `AutoRotatorSystem` (`Assets/Scripts/FFSystems/Utils/AutoRotatorSystem.cs`, FFFixedPreTransformGroup,
    write at :137). It draws each spin rate from a random seeded with the Entity handle (:112-118), and Entity handles
    differ between peers.
  - The fingerprint does not hash this rotation: 2777, 7285 and 4182 heartbeats compared clean. So strip `Rotation` on
    those entities before you diff dumps, or a mod looks guilty.
  - Its comment says no simulation system reads the rotation. A code read found that `FpCollisionWorldBuildSystem`
    builds the fragment's Collider child pose from it (:347-352). That is an open base-game question, and it is
    unproven as a desync.
- **A built host waits only 900 s for its client** (`waiting-host-peers-connected` timeoutSeconds=900). Set up the
  scenario well inside that, or have the client join first and drive the host after the join.
- **Fuel scenarios:**
  - Laser Turrets burn no fuel in this version (`LaserTurretConfig.asset` `ValidFuel: []`), whatever a mod's
    description says.
  - A Rocket Adapter burns Connectors only while its station flies (`RocketAdapterFuelConsumerSystem.cs:105`). Place
    `ValidationScenarios/mobilestations/station-rocket.ffbp.txt` with `blueprint.place`, then load fuel with
    `station.put|<core x>|<core z>|Rocket Adapter|Connector|10`. Keep the station moving with
    `mobilestation.movenow|<core x>|<core z>|<dest x world>|<dest z world>` every 12 s. The ref stays the Command Core's
    original tile while the station flies.
- **Dump each epoch on its own.** A client's join resets the heartbeat counter, so the host's dump holds an epoch-0 run
  before the join. Compare only the blocks after the last reset, and only heartbeats both peers dumped.
