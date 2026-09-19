---
name: loader-reinstantiates-prefab-baked-save-components-return
description: "SaveGameManager restores an entity by Instantiate(itemPrefab) and then only ADDS the saved components the prefab lacks (SaveGameManager.cs:1313-1330, 1436) — it never removes a prefab-baked [Save] component the save omits. So any marker the LIVE path strips from a prefab-based entity comes back on every load, and every loading peer (join, recovery, resumed save) differs from the peer that created it live. 074 T108: KnnFleetEntity on an unbuilt construction site — census red every heartbeat until the build, and a KNN fleet source on one peer only. Fix pattern: a SerializationHelperSystem in the restoration sequence that re-applies the live path's strip."
---

# The loader re-instantiates the prefab, and baked `[Save]` components the save omits come back

**Mechanism (path-traced 2026-09-19).** `SaveGameManager.InstantiateEntity` does
`entityManager.Instantiate(itemPrefab)` (`SaveGameManager.cs:1436`), then the restore loop scans
the saved component set and ADDS the missing types in batches (`:1313-1330`) before overlaying
the saved bytes. Nothing removes a baked component that the saved entity did NOT carry. A
component the live path REMOVES from a prefab instance is therefore absent in the save and present
again after every load. Generic stripping ("remove every `[Save]` type the save lacks") is NOT the
fix: a `[Save]` component added to a prefab after the save was written must survive the load.

**The instance (074 T108).** A construction site is instantiated from the item prefab and
`KnnFleetEntity` is stripped at once (`BlueprintInstantiatorSystem.cs:364`, again on confirm
`BlueprintPlacementSystem.cs:838`); `ConstructionBotTaskSystem.SetUpComponentsOnNewlyAddedStructure`
(`:221,236`) re-adds it when the build completes. So the placing peer's site has no marker, the
save has none, and every peer that LOADS the world (join snapshot, desync-recovery apply, a host
resuming a save) gets a site WITH it: `census` unequal on every heartbeat until the build finishes
— on built players both t6 clients were kicked within 13 hb, so it looked permanent — and the site
was in the fleet KNN tree on one peer only (a real simulation asymmetry, never a census-strip
candidate). Fix `168f37837`: `ConstructionSiteKnnReconciliationSystem` (a `SerializationHelperSystem`
in the restoration sequence, every peer — a load-shape repair, not a mint, so no
`AppliesRemoteAuthoritativeWorld` decline) strips it from `OutOfPlay`+`ConstructionTaskData`
entities; guard `ConstructionSiteKnnReconciliationSystemTest` incl. a source census that
`SaveGameManager` runs it. Every file touching `KnnFleetEntity` also needs a row in
`CombatMoverProviderCatalogTest` (055 vision-producer catalog) — `RemoverOnly` here.

**How to recognise the class.** A loaded entity forks against its live twin by ONE component
that is baked on its prefab; grep the live creation path for `RemoveComponent<That>` — if the
live path strips it, this is the class. Ruled out first on T108, in order: the combat-identity
mint (declined on remote apply — `RemoteAuthorityApply pendingRoots=N` in the client report),
recovery leftovers (a solo save→load differed only by that host-side mint), the T105 material
children. Related: [[join-load-route-provisioning-desync-class]] (load-route asymmetries),
[[editor-pair-per-heartbeat-census-hook]] (the instrument that named the row).
