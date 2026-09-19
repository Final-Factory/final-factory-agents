---
name: material-property-overrides-fork-the-census
description: "074 T105: the peer that ORIGINATES a mining/research-station placement (mouse preview or ffauto construction.place) runs the terrain-extractor finder on its blueprint ghost, which instantiates the LogisticsRouteDisplay prefab as a child; its children carry only [MaterialProperty] components (BaseColor/ArrowAngle/ArrowOffset, FF namespaces) so the census counted them, remote peers never create the display (the marker-armed finder returns before CreateRouteDisplay) and a recovered peer rebuilds children from the prefab -- a permanent census fork on both clients from the first placement that survived two successful recoveries. Rule since 246653207: any type carrying Unity.Rendering.MaterialPropertyAttribute is stripped (CensusTypePolicy.IsKept). T103 is the sibling: per-load report singletons. Diagnostic recipe: fielddiff.py over the continuous reports, then a single-player editor probe diffing CollectCensusRecords(em, true) before/after the same ffauto command."
---

# Material-property overrides fork the census (074 T105, 2026-09-19)

**Signature.** Right after the host's first `construction.place` of a Mining Station both clients
verdict `census` (index 21) — and after a successful recovery the census is red on EVERY heartbeat,
both clients on the same hash ≠ host. `fielddiff.py` (074 lab) over the continuous cp reports: epoch
2 equal to hb 10101, unequal from 10102 (the apply heartbeat); epoch 4 unequal 1–2100 on both pairs.
Only `census` moved.

**Mechanism.** `ExecuteConstructionPlace` runs `TerrainExtractorTerrainItemFinderSystem` synchronously
on the ghost (the interactive preview runs it every heartbeat); with no marker present it calls
`CreateRouteDisplay`, instantiating `Assets/Prefabs/EffectsEntities/LogisticsRouteDisplay.prefab` as
a LinkedEntityGroup child of the ghost, which then becomes the station. The root is already stripped
(`ArrowDisplayMetaData`, `LogisticsDisplayReferences`), but the five children survive on
`BaseColorMaterialProperty` / `ArrowAngleMaterialProperty` / `ArrowOffsetMaterialProperty` alone —
FF namespaces, so the census kept them. Remote peers apply via `EnsureTerrainExtractorTargets`, which
arms `TerrainItemFinderMarker`; the finder resolves the target and queues the marker's removal through
the ECB, but its lookup still sees the marker at the `return` before `CreateRouteDisplay`, and next
heartbeat the entity no longer matches the finder query — no display, ever. A recovered peer rebuilds
the station's children from the prefab — no display either. `BaseColorMaterialProperty` is even
`[Save]`, which does not help: the display is not a saved entity.

**Fix shape (the T103 shape generalised).** `CensusTypePolicy.IsKept` strips any component whose type
carries `Unity.Rendering.MaterialPropertyAttribute`, matched by attribute NAME (FFSystems has no
Entities Graphics reference). A GPU material input is presentation whatever namespace holds it; the
next prefab with an override can no longer reopen the bug. Guard:
`CensusFingerprintTest.CensusHash_IgnoresMaterialPropertyOverrides`. T103 (`64df62b5f`) is the
sibling: `CombatLegacyMigrationReport` + `PlayerStationGridMailboxRepairReport` exist on every LOADED
world and never on a GENERATED one, so a new-game host forked from hb 1 against every joined client.

**Diagnostic recipe that found it in ~10 minutes, no diagnostic leg.** (1) `fielddiff.py HOST CLIENT
EPOCH` over the cp reports: which surface, which heartbeat it forked, whether it heals — a
post-recovery `cp3.sh` is `evidence-invalid` by design, but the per-hb `Fingerprint.fields` are all
there. (2) Single-player editor probe (Ben's rule: diagnose live before another paired leg): load the
leg's own checkpoint (`SaveGameManager.LoadGame(LobbyCreationParameters.SinglePlayerGame, name,
true)` + pumped `EditorApplication.Step()` until `ConfigInitializerSystem.GameStarted && MePlayer &&
hb > 40`), dump `DeterminismStateFingerprintJobs.CollectCensusRecords(em, true)` (internal — reflect)
to a file, run the same `ffauto:` command through `LocalMultiplayerAutomationCommandRunner.TryExecute`,
pump 40 frames, dump again; the live diff names the signature and its type list. The `CensusDetail`
diagnostic profile ([[diagnostic-profile-config-recipe]]) is the fallback when the fork needs a peer.

**Not fixed (presentation, pre-existing).** Remote peers and loaded games never show the
station→asteroid route arrow.
