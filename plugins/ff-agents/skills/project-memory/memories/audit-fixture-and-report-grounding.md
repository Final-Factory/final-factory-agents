# Audit fixtures and report grounding (2026-09-05)

Source-count agreement is useful for a focused diagnostic, but it never waives the full
fingerprint comparator. Preserve the return code from `run_knn_membership_audit.sh` during a focused
diagnostic run and its test run; use the full comparator to establish parity. The current cross-platform
result is 637 shared Windows/Mac reports with normalized full parity. Sources:
`scripts/audit/run_knn_membership_audit.sh` and `scripts/audit/test_knn_membership_audit.sh`;
`scripts/audit/determinism_audit_lib.sh` — `da_extract_fingerprints` and
`da_assert_field_aligned`; its test is `scripts/audit/test_determinism_audit_lib.sh`.

The observed instant-placement fixture had no construction tasks. A waiting join fixture must invoke
the real `BlueprintPlacementNetworkOperation.EnsureConstructionTasks`, then assert `OutOfPlay`,
`ConstructionTaskData`, and no KNN before the join. Do not use an instant-placement fixture as
evidence about this path. Source: `Assets/Scripts/GameRunning/TestModeInitializer.cs` —
`SetupBlueprintWaiting`; `Assets/Scripts/NetworkOperations/Blueprints/BlueprintPlacementNetworkOperation.cs`
— `EnsureConstructionTasks`.

Inspect the baked `ItemConfig.ItemPrefabs` component matrix before alleging that a loader re-added
KNN. In the observed matrix at revision `7d696256c`, Connector 40 carried no KNN, so the old green
result was not a valid witness. Strut 186 did carry KNN; the waiting and control positive cases had
1,470 and 1,471 shared heartbeats, respectively. The actual pre-filter Strut RED is still pending
and must not be reported as proven. Source symbol: `ItemConfig.ItemPrefabs`; observed-matrix and
fixture evidence: `specs/055-combat-mover-vision/plan.md` (updates at lines 70–97).

Cross-platform extraction may normalize CRLF only at the extractor's line end. Preserve the source
report bytes. Keep tests for mixed LF/CRLF inputs and real fingerprint mismatches so formatting
tolerance cannot hide a different report. Source: `scripts/audit/determinism_audit_lib.sh` —
`da_extract_fingerprints_with_epoch`; tests: `scripts/audit/test_determinism_audit_lib.sh` test 21.

A written report is not proof of a successful player exit. Keep each native player as an owned
child, wait for its actual status, and require natural exit zero for both peers. A wrapper that
kills players after collecting reports can conceal teardown failures. Preserve reports when
exits fail; parity and process completion are separate gates. Source:
`scripts/audit/run_build_multiplayer_audit.sh` — `await_run_players` (revision `1f8b4f56b`).

A placed blueprint does not prove its power topology works. Inspect actual grid membership and
nonzero power before using it as a regression fixture. The nine-structure distributor fixture
uses Trash hubs to connect each solar panel and distributor; ordinary removal needs a spawned
Construction Bot and enough time to complete the task. Require ordered functional observations
in addition to full peer fingerprints. Sources: `scripts/audit/run_power_distributor_audit.sh`
and `specs/065-power-distributor-many-to-one/plan.md` (revision `c66abb571`).

Event cleanup must match the cadence of its consumers and retire only events visible to that
update. A controller-frame cleanup can erase work before heartbeat consumers run. Destruction
using a query evaluated at command-buffer playback can also erase new events queued into that
same buffer, before any consumer sees them. Snapshot the existing entity set instead. Both
power refresh and funded attack events exposed this failure; preserve their lifetime regression
tests when changing cleanup or producer ordering. Sources: `EventCleanupSystem<T>.PerformSystemUpdate`,
`PowerTransmitterEventCleanupSystem`, `PowerTransmitterEventLifetimeTest`, and
`AttackEventLifetimeTest` (game revision `228a6e69a`). The unit regressions passed there; the
live Dyson receiver replacement still requires its separate paired verification.

## Charge fixtures (2026-09-06)

A prefab authoring-file search is not a complete component census. Configuration initialization
can add components to item prefabs: `ConfigLoadingUtil.InitializePowerComponents` adds
`ChargeConsumer` when the configured consumption rate is positive. Inspect the initialized
`ItemConfig.ItemPrefabs` or placed entity before concluding a consumer is absent. Source:
`Assets/Scripts/Helpers/ConfigLoadingUtil.cs`, `InitializePowerComponents`.

Verify actual grid membership, ordinary demand and output filters before blaming gameplay code.
A Spawner Chest also supplies 500 power, making it unsuitable as the direct feeder of a
charge-starvation fixture. Adjacent independent modules do not automatically form one grid.
A mass-driver output connector with no selected item is deliberately set to `FilterAll`;
set an explicit item in the blueprint or through the normal networked setting operation.
Sources: `StationGridMembershipSystem`, `ConnectorPostPlacementSystem.ConnectorPostPlacementJob.Execute`,
`ForceFilterSystem.ForceFilter`, and the live matrix in
`specs/066-laser-turret-charge-never-deducted/plan.md`. The accepted fixture is
`ValidationScenarios/charge/charged-driver.ffbp.txt` (game commit `acda1152e`).

Size the supply using the actual timer gates: `MassDriverSystem.MassDriveTimerJob.Execute`
compares the same timer with both RearmTime and LoadTime, so rearm is part of the loading cycle.
A fixture that shows grants and deliveries may still never exhaust charge. Require each peer
to witness storage decrease, a denied positive-cost attempt, recharge, a renewed grant, and a
later inventory increase, in addition to the full comparator. Compare the delivery with a
baseline at or after the renewed grant; an earlier delivery must not satisfy that stage.
Sources: `scripts/audit/assert_charge_observations.py`, `scripts/audit/run_charge_settlement_audit.sh`.

Budget instrumentation as well as simulation time. `NetworkDeterminismAudit.MaxCriticalEvents`
is 256, shared with lifecycle and operation evidence; exceeding it fails the strict verdict.
The charge wrapper records 64 groups of three adjacent inspections (192 records), with 1.61-second
waits to avoid sampling only one grid-calculation phase. Adjacent instantaneous bootstrap commands
run in one heartbeat (`LocalMultiplayerAutomationBootstrap.ExecuteChainedCommandsAsync`). Install
an early sampler before setting AutoStartInEditor true: merely writing an armed automation config
can enter Play before a separate editor-play command. Preserve the raw reports and natural exits.


## Mac standalone artifact status (2026-09-06)

A standalone run rewrites `.ff-local-automation-status.json` inside the selected Mac `.app` root.
`LocalMultiplayerAutomationSessionConfigStore.GetCurrentProjectRoot` derives that location from
`Application.dataPath`; changing the process working directory does not fix it. Windows runtime
files live at the build root. Artifact identity excludes only the two exact automation config/status
filenames at those known locations. Executable/data bytes and same-named files elsewhere remain
hashed. Keep writer and validator aligned (`run_determinism_testcases.sh`, `run_cross_platform_peer.py`);
the fake-peer regression proves repeated runs and rejects real-data tampering.

If an old manifest counted runtime status, preserve the original manifest, changed status and
pre-correction identity outside the artifact. Identify the specific mutation, correct metadata under
explicit old-hash preconditions, record the new identity/provenance, and revalidate after the next run.
Never silently accept a mismatch or claim the old hash still holds. The charge audit exposed a
15-byte status change among 524 files; excluding that exact runtime file leaves 523 static files.
No simulation comparison is waived. Source: feature 066 plan and the manifest adapter regression.


## Startup and restore witnesses (2026-09-06)

Before calling `SaveGameManager.LoadGame` in a newly entered editor session, require completed
`StartController` startup, a real `ItemConfig` singleton, and the title-screen dependencies such
as `Hotbar.Instance`. `StartController.Loaded` alone is insufficient: it is set in `finally`,
including after initialization failure (`StartController.cs:507-517`). Check the fresh startup
errors too. A premature call can fail in `TitleScreenManager.PrepareSceneForGame` and leave
`SaveProcessState.Performing` without ever opening the archive. CPU activity and changing RSS
are not proof of forward load progress. Read the archive/stage counters and actual entity count;
label the attempt a harness failure when archive reading never began.

A restore comparison must exercise capture, actual ECS loading and production grid reconstruction.
`GoldenSaveFixtureManifest.Decode` is an archive census; even its columnar-fast branch materializes
payloads for inspection and never creates ECS entities. Compare the retained host after reset with
the reconstructed client after reset: `GameStateRpcManager.ServeSaveFileWhenHostReady` resets all
peers before capturing. Preserve the existing forced recharge behavior. Advance mature fixtures
through every intervening heartbeat; jumping directly to each phase does not exercise its history.
Assert the reset flag immediately after consumption, rather than clearing it in the test loop.
Source: `ChargeRestoreRoundTripTest.CapturedChargeState_RebuiltGridMatchesMatureGridAfterSymmetricReset`
(game commit `bc2dde97a`). Synthetic stale receipts do not establish authentic old-save provenance.

For the small laser depletion fixture, place Laser(0,0), Capacitor(0,1), and an Up-facing Solar at
(0,-2). The solar is two tiles long and must connect directly to the turret; putting it behind the
capacitor or at(0,-1) leaves a separate grid. Verify actual membership before adding the target.
Use ordinary `GameInitializer.SetGameplaySettings` with `DisableEnemies` before manually placing
Razor Spawner; `DisableEnemyGeneration` does not prevent that spawner producing ships
(`EnemyShipSpawnerSystem.OnUpdate`). Record actual target health with paid/denied charge and
storage, not just the beam. Input: `ValidationScenarios/charge/laser-depletion.ffbp.txt`; solo
proof and its limits are in feature066's plan at `bc2dde97a`.
