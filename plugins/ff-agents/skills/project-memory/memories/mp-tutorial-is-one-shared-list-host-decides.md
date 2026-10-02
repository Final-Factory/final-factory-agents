---
name: mp-tutorial-is-one-shared-list-host-decides
description: "w175 (#893, 2026-10-02): the tutorial/objectives are ONE shared list. Only the host (or single player) runs verifiers and initiators and authors ObjectiveProgress (71 request / 72 apply); every peer changes its lists only when that op drains; any player's action counts; Complete (skip) is a request, one step for everyone. Counters are written only by ObjectiveCounters.TryAdd from apply legs. Also: a client-created singleton survives the load wipe; MonoBehaviour.Reset fires on AddComponent in EditMode; ui.click right after a step completes hits the old card; -ffAutomationTutorial / world.tutorial; the title menu cannot be driven over the agent channel."
---

# The MP tutorial is one shared list and the host decides (w175, PR #893, 2026-10-02)

**The model now.** `ObjectivesController.Tick` on the host (or the single player) is the only place
verifiers and initiators run. What it finds goes out as `ObjectiveProgress` (request 71, apply 72);
every peer, the host included, moves its completed/active lists only in `ObjectivesController.Apply`.
Any player's action completes a step: the host-player checks iterate `ObjectiveHelpers.SessionPlayers`.
The Complete (skip) button is `ObjectiveSimulationAuthoring.RequestSkip`: one click on any peer moves
every peer by exactly one step, no achievement. This replaces 022 D1 (host-driven, per-peer copies).

**Counters.** `ObjectivesTracker.FrenzyUsed` etc. are written only by `ObjectiveCounters.TryAdd`, from
apply legs: Frenzy and Plasma where `PlayerAbilityFire` applies (accepted casts, any player), collected
items where `InventoryTransfer` applies, Afterburner/map/fleet panel/copy-paste via
`ObjectiveSimulationAuthoring.RequestCounter`. UI and input code never write the tracker.
`HostObjectivesTrackerProjection` and its RPCs are gone.

**What was broken, and the shapes to recognise again.**

- *Per-peer copies of shared state.* Each peer advanced its own lists; a skip moved one peer only.
  Tell: two peers showing different objective cards. Check `observe.state|objectives` on both.
- *A client-only singleton outlives its session.* The client created the projection entity from an RPC.
  `FinalFactoryGrid.DestroyGameEntities` is a fixed list of types, so nothing removed it, and the reader
  preferred it whenever it existed. A process that had been a client and then hosted read the old
  host's frozen counters: its own Frenzy never advanced on its own screen while its clients advanced.
  Any "prefer the projection if present" reader needs the projection destroyed at the load wipe.
- *A step checked before its own queued op applied.* "Destroy the enemy camp" starts by authoring the
  camp spawn (an op since `ae0623198`) and was checked in the same call; "no camp" read as "destroyed",
  so the step completed itself at once, single player too. Guard: `EnemyCampSpawnInFlight`.
- *In-flight age against the raw heartbeat counter.* A join resets `Heartbeat.CurrentHeartbeatFrame`
  to 0 while the host holds its drain. Measure age with `ObjectiveSimulationAuthoring.CurrentHeartbeat`
  (only grows), never `(ushort)(now - then)` on the raw counter.

**Test and harness traps.**

- `MonoBehaviour.Reset()` is a Unity editor message: `AddComponent` calls it in EditMode. A controller
  with its own public `Reset()` runs it before any test set-up; null-guard what it touches.
- `ffauto:ui.click|objectives|…/ObjectiveItem(Clone)/Controls/SkipButton` within about a second of the
  previous step completing resolves to the OLD card still animating out. The host refuses that stale
  skip and nothing moves. Wait ~1.6 s between clicks.
- Tutorial on for built pairs: `-ffAutomationTutorial true` on the host (ffnightly: `"world":
  {"tutorial": true}`). An older build without the flag: put `.ff-local-automation.json` (Role Host or
  Solo, `Tutorial: true`) in the player folder and start the host with no `-ffAutomationRole`.
- The agent channel refuses commands at the title menu (`state_not_playable`), so "leave a session,
  then host or start single player in the same process" cannot be driven in a built player. Prove that
  class in EditMode.
- Scenarios: `MP-tutorial-shared-progress`, `SP-tutorial-progress`. Proofs:
  `specs/w175-mp-tutorial-progress/proofs/`.
