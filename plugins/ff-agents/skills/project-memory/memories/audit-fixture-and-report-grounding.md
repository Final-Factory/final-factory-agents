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
in addition to full peer fingerprints. Sources: `scripts/audit/run_power_distribution_audit.sh`
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
