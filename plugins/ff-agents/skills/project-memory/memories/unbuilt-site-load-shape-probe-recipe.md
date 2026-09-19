---
name: unbuilt-site-load-shape-probe-recipe
description: "To hold a construction site unbuilt for an arbitrary window, `construction.place` with NO copy of the item in the host inventory: the ghost commits as state `frame` (activeTask AddStation) and never builds — with the item present a cbot beside the player built it in 9 heartbeats and an inject-then-recover proof landed on a BUILT station. `game.save` that world, resume it as an editor host, join a clone, and one execute_code entity probe per editor answers a load-shape question; the census hook is only for finding WHICH row differs. Comets are never marshalled (074 T110)."
---

# Unbuilt-site load-shape probe recipe (074 T108/T110, 2026-09-19)

**The window.** A Mining Station placed from the built host at 07:46 UTC was `building` at
hb 1564 and `built` at hb 1573 — a construction bot next to the player finishes a site in ~9
heartbeats, so the client recovery injected 0.3 s after the placement (verdict hb 1576) served a
snapshot with a BUILT station and proved nothing about sites. `construction.place` with NO copy
of the item in the placing player's inventory commits the ghost as state `frame`
(`snapshot/nearby` shows `"state":"frame","activeTask":"AddStation"`) and it stays unbuilt
indefinitely (still a frame 20,000 hb later). That is the reliable window for any
load-shape question about sites. Note the placed `GridTile` can differ from the requested tile
by one (asked -54,-16, landed -55,-16).

**The probe.** `game.save|<name>` on the host that holds the frame; copy the zip + sha256 to the
lab `saves/`. Then on the editor pair (both preflight-pass, both proven on the fix build —
[[stale-clone-editor-invalidates-pair-evidence]]): host `.ff-local-automation.json` resuming
that save (`Port 7777`, `TargetClientCount 1`, `ExitPlayModeOnComplete false`, long
`PostConnectDelayMs`); it reaches `waiting-audit-dwell-release` in ~10 s and accepts the clone
there. Write the clone's client config, wait for its `waiting-audit-dwell-release`, then ONE
`execute_code` on each editor:
`EntityQuery(OutOfPlay, ConstructionTaskData)` → per entity `HasComponent<KnnFleetEntity>()`,
plus `World.GetExistingSystemManaged<TheFixSystem>()` `Enabled`/`Run`, plus any other
row-in-question count (`EntityQuery(Comet)`). Host resume and clone join are both LOAD paths;
the built host that placed it live is the reference. The per-heartbeat census hook
([[editor-pair-per-heartbeat-census-hook]]) is the tool for finding WHICH row differs when you
do not yet know; once you know the row, the direct probe is one call and cannot be fooled by a
cold Burst cache.

**Comets (074 T110).** The same p4 dumps showed a host-only `[LinearMotion, Comet]` row on every
heartbeat: `MarshallingSystem.cs:172-182` assigns an `EntityType` only to `AsteroItem` entities
and players and `:210` marshals only those, so the `[Save]` `Comet` (prefab
`Assets/Prefabs/Comet.prefab`, `LimitedLifetime` 60 s) is never in a save or snapshot. Every
loading peer lacks an in-flight comet until it dies; on built players that was a `census` fork
of exactly hb 1–500 of the recovery epoch that healed on its own with no second verdict. A fork
that heals by itself after a few hundred heartbeats with no re-fire is that shape.
