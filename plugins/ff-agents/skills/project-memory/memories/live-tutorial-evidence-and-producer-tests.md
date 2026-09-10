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
`FleetMoverInputDiagnostics.DescribePhysicsBody`.
