---
name: marker-consumers-must-clear-the-whole-station-in-one-heartbeat
description: "A [Save]d work marker that a producer sets on MANY entities at once and a consumer clears ONE entity per Execute (returning early for the rest) drains one per heartbeat in chunk-iteration order — archetype-creation order, per peer. The census counts the marker, so the peers' marked sets differ on every heartbeat until the drain finishes, and never finish while gameplay keeps refilling it. 073 T032: RecalculateHaulersMarker on the hazel1831 base (67 pending SwapItem upgrades), both peers held the same ~30 marked structures on the same heartbeats and cleared a DIFFERENT one each heartbeat. Fixed 6384314c5 by clearing every structure of the recomputed station in one Execute. Includes the timeline recipe that replaced a paired leg."
---

# Marker consumers must clear the whole station in one heartbeat (073 T032, 2026-09-18)

**The shape.** Producer: `PlaceableDeletionSystem.cs:301-304` adds `RecalculateHaulersMarker` to EVERY live
hauler-referencing structure connected to a deleted placeable (the whole base). Consumer:
`MoveableStructurePostConnectionSystem` (`FFFixedPostTransformGroup`) recomputes the station once per heartbeat from
the first marked structure its query iterates, cleared the marker from THAT structure only, and returned early for
the rest (`Visited`, `:92`). The set therefore drained one marker per heartbeat, and WHICH one is chunk-iteration
order = archetype-creation order ([[ecs-iteration-order-is-archetype-creation-order]]) = per peer. The marker is
`[Save]`d and the `census` surface counts it.

**The tell.** In `CensusDetail`, the same structures sit in two signatures differing only by the marker, with the
per-signature counts summing to the same total on both peers (host 9+1 / client 10+0) — a MEMBERSHIP difference
at equal cardinality. A per-heartbeat timeline of "entities carrying the marker" shows identical counts and sets on
both peers, dropping by exactly one per heartbeat between refills, then the same count with different members.
Post-recovery the census is red on every heartbeat for as long as gameplay keeps refilling the set (67 pending
Solar Panel SwapItem upgrades on hazel1831 → 4,476 red heartbeats), which looks like an unsaved per-peer tag
([[per-peer-gates-on-structural-changes-fork-the-census]]) but is not — the tag IS saved; the drain order is not.

**The fix shape.** One recompute clears the marker from every entity in the set it just covered (ECB
`RemoveComponent` on an entity lacking it is a no-op) so the marked set after any heartbeat is a function of the
shared sweeps, never of iteration order; and any choice the recompute makes from "the first entity I met" (here the
surviving hauler on a station without a command core) gets an order-free rule (bottom-left grid tile). Guard:
`RecalculateHaulersMarkerStationDrainTest` (5 marked structures → 0 after ONE update; the no-core survivor is the
same whichever structure is marked). Audit the class with `grep -rn "RemoveComponent<.*Marker>(entity)"` inside
`IJobEntity.Execute` bodies that also return early on a shared `Visited` set.

**Diagnose from the reports you already have.** The handoff read "set one heartbeat apart" from one `CensusDetail`
row; a 40-line script over the two `-early-report.log` files (`marker_timeline.py`: per heartbeat, sum `n` of the
signatures containing the type; flag heartbeats where any signature's `n` differs) showed identical sets for ten
heartbeats and the divergence as a drain-order split — no paired leg, no single-player probe, ~5 minutes. Before
scheduling another leg, ask what the existing diagnostic report can answer per heartbeat.

**Also learned.** The bridge's `execute_code` safety filter blocks `System.IO.Directory.Delete`; the one-shot Mac
player-build snippet now refuses when the output dir exists instead of deleting it. And the first `run_tests` job
started right after the post-test re-pin can be LOST ("Unknown job_id") — wait for
`~/.unity-mcp/unity-mcp-status-<hash>.json` fresh + `reloading:false` + the port open, re-pin by PORT, then start.

**What was left after the fix (T033).** Leg g12 on `6384314c5` still showed 4 isolated one-heartbeat `census` blips
(g12d: 6) — none involving this marker; every one was a just-swapped structure created through the EARLY buffer,
i.e. on the next ENGINE frame — [[fixed-group-ecb-must-play-back-later-in-the-same-frame]]. Fixed `1174e30bd`; leg
g13: 5,189 shared heartbeats, `census` equal on every one, 0 verdicts.
