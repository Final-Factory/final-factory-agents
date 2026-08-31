# Join/load-route provisioning is a desync class of its own

**Feature:** 055 combat-mover-vision, rounds R22–R31 (2026-08-29/30, `specs/055-combat-mover-vision/tasks.md`)

Seven distinct forks in one feature all reduced to the same shape: a player-owned or
load-time-installed component/id was provisioned on SOME arrival routes (fresh spawn, load, join)
but not others, or provisioned identically-but-differently-timed across peers. Each is its own bug
class; group-read this file before touching anything that installs per-player state, mints
canonical ids, or "heals"/"repairs" data during a load.

## 1. A load-time applier must run AFTER the serialization group, in the SAME heartbeat (R22)

`PlayerSimulationObjectIdentitySystem` copied a player's `DeterministicCombatObjectId` onto its
transient `PlayerSimulationObject`, but sat in `FFFixedInitializationGroup`
(`InitializationSystemGroup`) while a load lands in `FFControllerSerializationGroup`
(`SimulationSystemGroup`, strictly LATER in the same engine frame,
`SystemGroups.cs:23-24,228-230`). A player object created by a load therefore missed its own
heartbeat's identity copy — `C3VisionProvisioningSystem` correctly refused the unstamped object,
producing a one-heartbeat vision fork that "healed" the next tick, visible ONLY on a joining
client (the host had loaded hundreds of heartbeats earlier). Fix: move the copy pass to
`FFFixedPreTransformGroup`, `UpdateBefore` every provisioner that reads the id
(`PlayerSimulationObjectIdentitySystem.cs:74-76`). **Tell**: a fork that heals itself one heartbeat
later, present only on the peer that just joined/loaded — that shape means an applier one group
too early, not a missing component.

## 2. Never resolve-then-structurally-mutate inside one ComponentLookup loop; paused-world systems need explicit force-enable (R22b)

`PlayerSimulationObjectIdentitySystem.OnUpdate` did `ComponentLookup.TryGetComponent` then
`EntityManager.AddComponentData` (a structural change) inside the SAME loop iteration. The
structural change invalidates every outstanding `ComponentLookup`, so a second loop iteration threw
`ObjectDisposedException`, silently swallowed as a logged system exception. It never reproduced
solo (one unstamped object per world never reaches a second iteration) — only on a join, where the
host's and the joiner's own simulation objects are both unstamped on the same pass. Fix: resolve
every copy into a `NativeList` first, then apply them all in a second, non-interleaved pass.

Separately: a world apply runs with the game PAUSED (`SystemManager.PauseAllFFSystems` clears
`SystemState.Enabled` on every `FFSystems.*` system by substring), so a plain `SystemHandle.Update`
called synchronously from the load path — needed here because the heartbeat can't cover the gap
above — is a SILENT no-op. `CombatLoadPathProvisioning` (new) force-enables each system for the
duration of the call and restores the flag afterward, same precedent as
`SaveGameManager.cs:2308-2311`'s `EnableSystem("NetworkedInventoryCacheUpdaterSystem")`. **Tell**:
a load-path provisioning call that appears to run (no exception, no log) but visibly changes
nothing — check whether the world is paused and the system's `Enabled` flag before assuming the
logic is wrong.

## 3. Route-dependent component installation is a desync class on its own (R24)

`CombatProjectileBirthSystem`'s query demanded `DeterministicShotSequence`, which was installed in
exactly two places — the load-time legacy migration and one placement network op — and NOT by the
one system (`PlayerAbilityStateInstallSystem`) that installs every other player-ability component
on every arrival route. Whether a player could birth a projectile therefore depended on whether
that peer happened to run a LOAD after the player was created — an accident of arrival route, not
agreed state. Fix: install the fourth record on the same `WithAll<Player>` shape as the other
three, on every peer, seeded explicitly (not left at the zero `AddComponent` default — the
migration seeds a different starting ordinal, and a mismatched seed mints two different keys for
one agreed event). **Rule**: every per-player/per-entity component needs exactly ONE installer
that every peer evaluates identically, regardless of whether that peer arrived via spawn, load, or
join. If you find a component added in more than one place, that is the desync waiting to happen —
route eligibility must never be a function of local load history.

## 4. An allocator must advance by ids WRITTEN, not ids RESERVED (R26)

`CombatIdentityAssignmentSystem` sized its reservation batch by the count of PENDING identity
stamps, then threw away any mint whose target already had an id (`if
(!HasComponent<DeterministicCombatObjectId>)`) — but the counter had already moved. On a JOIN, the
joining client loads a player entity whose id a load-path migration already minted while the
`[Save]`d `PendingCombatIdentity` stamp survived the round-trip; draining that stamp burns an id on
the joiner that the host (which never loaded) never burns. From that heartbeat the two allocators
are permanently offset by one, and EVERY later spawn keys differently on the two peers even though
every other folded field agrees — which is why this class only shows up on id-keyed surfaces
(`movers`, `vision`, anything folding `CanonicalDynamicKey(objectId)`) and nothing else. Fix:
build the batch from entities that do NOT already carry the id, so the sequence advances by ids
actually WRITTEN — the drain becomes idempotent over deserialized state, which any `[Save]`d stamp
replayed by a load requires. **Tell**: every folded FIELD is byte-identical between peers but a
`movers`/`vision`-class surface still forks — suspect the object-id allocator before any field.

## 5. A controller-group system feeding a fixed-group consumer is a presentation→simulation leak (R27)

`FleetCommanderSystem` sampled a player commander's PRESENTATION transform/velocity every render
frame and published it into `FleetCommander`, which the heartbeat-driven `FleetIdleSystem` then
read to steer every idle ship in that player's formation — a controller-group (per-frame) write
feeding a fixed-group (heartbeat) read, even though both systems look like ordinary "gameplay"
code. Fix: move `FleetCommanderSystem` itself into `FFFixedPreTransformGroup`, sampling
`Player.SimulationPosition` (replicated, heartbeat-authoritative) instead. **Audit technique**:
grep `FFControllerPreTransformGroup`/`FFControllerEarlyGroup` writers for any component also read
by a system in an `FFFixed*Group` — that pairing is the leak, independent of whether either system
"looks like" presentation code.

## 6. A "heal on load" pass must decline on a remote-authoritative snapshot apply (R28, R29)

Two migrations wrote unconditionally on every peer that LOADS: `CombatLegacyMigrationSystem` mints
combat ids/rails for legacy unmigrated movers, and `EnemyCampRestorationSystem` re-derives a
spawner's `SpawnStartingSetOfUnitsNextTick` arm flag from roster evidence (a 038 legacy-save
repair). Both are correct "heal a genuinely old save" passes — and both fork when the JOINING
CLIENT runs one over a snapshot from a host that never itself loaded (a fresh-world host, or a
spawner built mid-session after the fixture's last save): the joiner "heals" fields the host holds
unhealed, since a load-time repair pass and a join snapshot-apply share the same code path
(`SaveGameManager.LoadGameStateFn`) but only one of them means "this world genuinely predates the
fix." The host is authoritative for every `[Save]`d field; a client-only delta appearing at
heartbeat 1 of a join is the signature. Fix, same shape both times: a new
`AppliesRemoteAuthoritativeWorld` property on the system, read-and-cleared at the top of
`OnUpdateImpl` (mirrors `SerializationHelperSystem.Run`'s pattern), armed from `!isHost` at the one
call site in `SaveGameManager.cs` — when set, the repair is skipped and a typed decline is recorded
instead of running. **Rule**: any pass whose job is to backfill/repair data on a LOADED world must
ask "am I the host's own load, or am I applying someone else's already-resolved snapshot?" before
writing — the second case must always decline, because the host's state (healed or not) is already
the agreed answer.

**The mint doesn't have to live in a named migration SYSTEM (R31).** `SaveGameManager.RestoreProjectiles`
migrates any saved in-flight record whose `RailSchemaVersion` is 0 (`SaveGameManager.cs:1533-1541`),
and that migration calls `AllocateLegacyProjectileEmitterId` (`SaveGameManager.cs:1637-1694`), which
mints a `CombatObjectId` and advances `NextObjectId` on the world sequence — the same allocator-offset
shape as case 6, but the write sits in `SaveGameManager` itself, not in a system with its own
`AppliesRemoteAuthoritativeWorld` flag, so the R28 sweep missed it. Fix: thread the same `isHost ==
false` signal down `LoadGameAsync -> RecreateEntities -> RestoreProjectiles` and, on a
remote-authoritative apply, install nothing for a schema-0 record — `ProjectileSystem`'s rail-less
backstop seeds it on the next heartbeat from the same durable float pair the authoritative peer used,
so both peers converge on identical code instead of two expressions that happen to agree. **Rule**:
the R28/R29 decline sweep must cover every LOAD-PATH WRITER of `[Save]`d state that can mint an id or
rewrite a flag — not just the systems named "migration" or "restoration". Grep `SaveGameManager.cs`'s
own load path, not only `FFSystems`, for anything that allocates on a schema/version check.

## 7. Equal `Src` counts with unequal `Links` means cold INPUT, not a cold index (R30)

A joining client's movers/vision comparison surface can show identical source counts on both peers
but a diverging link count — the earlier cases in this file are about a cold ALLOCATOR or a
cold/declined WRITER, but this shape is a cold READER. `PlayerSimulationObject` is not `[Save]`d, so
every world apply re-instantiates it from the player prefab at `LocalTransform.Identity`
(`PlayerSimulationObject.cs:79-80`); the only system that ever places it,
`PlayerSimulationObjectPositionSystem`, is heartbeat-cadenced in `FFFixedPreTransformGroup`, while the
legacy `KnnSystem` runs a whole group earlier (`FFFixedEarlyGroup`, `OrderFirst`) and gathers its
source points from `LocalToWorld`. The first heartbeat of a freshly applied world therefore indexes
the player at the origin — and because `AssignVisionJob` breaks out of the neighbour walk at the
first point beyond `Range`, that reads as a disappearance, not an inaccuracy: host `fleetLinks=15` vs
client `fleetLinks=0` at heartbeat 1, equal from heartbeat 2 on. A long-running peer never sees it,
because its player object was placed hundreds of heartbeats ago. Fix (`LegacyKnnLoadPathWarmup.cs`,
new): run one warm-up pass immediately after a load, before the first fixed pass, so the legacy index
is built from placed positions on heartbeat 1 instead of prefab-spawn defaults. **Tell**: `Src` counts
agree (nothing was skipped building the index) but `Links` disagree at heartbeat 1 only, self-healing
by heartbeat 2 — that shape is a not-`[Save]`d, prefab-spawned entity feeding an early-group consumer
before its own positioning system has run, not a missing/duplicate index entry.
