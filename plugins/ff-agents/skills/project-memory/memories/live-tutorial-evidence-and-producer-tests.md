---
description: "Long tutorial acceptance needs real two-machine play, continuous evidence retained until completion, and tests that schedule the producer rather than only its shared helper."
---

# Live tutorial evidence and producer tests

The co-op tutorial ends when both players finish it. There is no 30-minute cutoff. Use continuous
verification for the whole run, then keep the reports, journals, terminal logs, screenshots and
objective snapshots. A clean report proves the declared simulation prefix; tutorial completion
still needs real input and inspected output from both players
(`Documentation/Continuous-Verification.md:3-20,38-40`). Follow
[cross-machine built-player gameplay acceptance](cross-machine-built-player-gameplay-acceptance.md)
for the gate.

`ProjectileMovementTest`
`AiFirePathBirthsARailAndAdvancesTheShooterShotOrdinal` calls
`NewShootingSystem.CreateProjectileEntity` directly
(`Assets/Tests/Combat/ProjectileMovementTest.cs:767-816`), so it cannot catch the aiming and range
inputs chosen by `OldShootingSystem`. The presentation-position regression needed tests that
scheduled `OldShootingSystem`, played back its ECB, then ran the real `ProjectileSystem` fallback
(`Assets/Tests/Combat/OldShootingPlayerPresentationTest.cs:85-155,195-200`). Do not describe a shared-helper test as coverage of every producer.

For the Mac test lane, use a current non-upload Mac build. `BuildMacPlayerNoUpload` switches to the
standalone macOS target, refreshes assets, rebuilds addressables, checks that the committed scene is
not demo, and runs the normal player build (`Assets/Editor/BuildCommand2.cs:515-542`). The witnessed
artifact had matching 325-file manifests on both machines. Matching manifests are only preflight: both players must use real input, and both sets of screenshots must be opened and read.

The automation bootstrap waits for the dwell release, performs its configured dwell, waits for the
teardown release, and then writes the automatic report on both host and client
(`Assets/Scripts/Behaviours/Multiplayer/LocalMultiplayerAutomationBootstrap.cs:603-630,748-762`).
Publishing both gates immediately with a short dwell therefore produces an early automatic report;
it does not mark a live tutorial complete. A menu-time `audit.write` can instead fail with HTTP 409
`state_not_playable` before the command runner is entered; that reason belongs to the agent-channel
router (`Assets/Scripts/Behaviours/Multiplayer/ActorContext.cs:131-136`). Preserve the full terminal
logs and continuous journals after either result. Do not treat an early checkpoint or early automatic
publication as the terminal tutorial report.

Transfer a report into a task-owned `.partial` path, verify its hash, then atomically rename it before
the parent reads it. This follows the same frozen-prefix and atomic-publication contract described in
`Documentation/Continuous-Verification.md:16-20` and avoids exposing a half-copied report.

Collision diagnostics must distinguish a raw raycast miss from a hit rejected by acceptance rules.
`LinearMotionStep.RayCastForWorldCollisions` returns false both when `PerformRaycast` misses and when
the raw hit is self or matches the fleet-ignore filter
(`Assets/Scripts/FFSystems/Core/LinearMotionSystem.cs:465-495`). Record the raw-hit result and the
rejection reason separately before assigning a gameplay cause.

When inspecting a collider blob, keep a reference: `ref var collider = ref body.Collider.Value`.
Do not copy its base `Collider` header into a local value before calling shape-dependent methods.
Unity Physics `Collider.GetCollisionFilter(ColliderKey)` fixes `&this` and casts it to the concrete
shape (`Unity.Physics/Collision/Colliders/Collider.cs:228-260`); that address must still point to
the full blob. The cached-body diagnostic uses the reference form in
`CachedPhysicsBodyDiagnostics.Describe`.

A collision world with no dynamic bodies can still be stale. In the September 10 two-Mac replay,
current owner transforms matched at heartbeat 75, but the host cache held heartbeat 73's pose and
the client cache held heartbeat 74's pose. The host then collided while the client accepted no
collision (feature069 plan, cached collision-body diagnostic). Test the actual builder and a
query result under different rendered-time sequences; a counter-only cadence test does not
prove transform freshness. `PhysicsWorldHeartbeatFreshnessTest` produced the real RED:
expected body pose `(20,0,0)`, actual cached pose `(0,0,0)` on the sub-timestep peer.

Order comments are not ordering edges. `FFControllerEarlyGroup` and Unity's fixed-physics group
both occupied the OrderFirst bucket, so their relative order needed an explicit `UpdateAfter`
and a real sorted-group test. Scope a freshness claim to the phases actually covered:
`ExecuteShipSpawnCommandSystem` also queries collision state during Initialization, before the
normal Simulation physics invocation.

A typed simulation pass is not an uninterrupted-connection verdict. The September 10
`live-heartbeat-physics-fixed011` replay matched all 5,898 shared samples across three epochs,
but the raw client log recorded repeated `WatchdogTripped` / `TransportLoss` reconnects.
Its automatic audit lifecycle still ended `clean-after-window`. Inspect both raw terminal
logs as well as the typed verdict; an epoch transition is not automatically a desync, and a
death screenshot does not establish why a client reconnected.

Checkpoint publication must not block the game thread. `ExecuteAuditWrite` formerly called
`WriteReportAsync(...).GetAwaiter().GetResult()`: moving disk work into `Task.Run` did not
unblock that caller. Large checkpoints preceded receive-queue-full messages and watchdog
reconnects in that replay. The command now attaches `ChainCompletion`, awaits publication,
and supplies its exact final path through `FinalResult`; `AutomationChainExecutor.AwaitSegmentAsync`
copies it into the terminal response. Test both pending completion and the returned path:
`AgentRequestRouter.LastResult` reads the step result, not completion detail. Keep an independent
timeout release in a held-publication test so a regressed synchronous wait cannot hang the editor.
The source correction and fast suite do not substitute for replaying a large checkpoint live.

Capture and inspect BOTH peers' final screenshots and copy/hash BOTH final reports before
stopping either player. Stopping the host while the client is still capturing can produce
a reconnecting overlay that obscures the actual terminal gameplay state. Keep each peer's
control owner responsible for its exact process, config and release gates until this shared
capture barrier is satisfied.

A fully matching simulation can still have a shared gameplay bug. In the September 10 fresh
`live-tutorial-resume011` run, all 8,637 shared heartbeats matched, yet both players received
four Bats without paying their raw-resource costs. Host logs rejected all eight consume
requests. `SmartCrafter.PerformSmartCraftHelper` passed zero-count intermediate removals to
`RemoveItemAndTrackInTree`, and `DispatchCollectedConsumes` included those entries in a payload
that `PlayerInventoryEditClientRequest.ValidateDeltas` correctly rejected. Inspect real
before/after inventory and fleet state, not only fingerprints or successful UI command receipts.
Regression tests must exercise the recursive crafting producer and actual host operation;
a hand-constructed valid payload cannot catch a producer emitting invalid entries.

For live UI placement, separate opening a panel, selecting a tab or inventory item, moving the
blueprint preview, and committing the placement with a rendered observation between dependent
steps. In `live-tutorial-craft-fixed011`, moving the preview and clicking in one immediate chain
left the replacement Mining Station unbuilt. A subsequent preview move, one-second wait,
inspected green ghost, and separate click produced the built station and advanced the objective.
This is observed harness sequencing, not proof that ordinary human placement is broken. Inspect
actual built state and the next objective after the click; a completed command receipt alone is
not a gameplay success. Dismiss the visible Technology Unlocked notification before crafting;
in the same run it covered the recipe panel and swallowed otherwise successful click dispatch.

Check the established gameplay contract before treating an unexpected inventory payer as a bug.
Construction deliberately services tasks from the shared nearby player pool:
`ConstructionTaskAssignerSystem.TryAssignPlayerBot:248-318` picks an eligible in-range player
holding the item and uses that player's available bot. The regression
`ConstructionTaskAssignerPlayerBotTest.PlayerBot_FallsThroughToInRangePlayerThatHasItem:87-102`
explicitly expects another eligible player to supply a task. In the live tutorial, a client-placed
Solar Panel consumed the host's held panel while the client retained theirs; the combined stock
fell by exactly one and the station became powered. Inspect both inventories and the chosen bot
before diagnosing duplication or a requester-ownership regression. A change to that shared-supply
contract is a design change, not a correction inferred merely from which peer clicked.
