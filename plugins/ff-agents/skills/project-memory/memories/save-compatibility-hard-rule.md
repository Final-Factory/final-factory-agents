---
name: save-compatibility-hard-rule
description: HARD RULE (Ben, 2026-09-28, after 0.50.0.45 could not load any 0.50.0.35..44 save) - every change to saved state ships with an UpgradeStep (or a proven no-op) and a golden-fixture load test; saves from master's current version and every beta since must load; plans carry a "Save compatibility" section and implement fails review without it
metadata:
  type: feedback
---

**Any change to saved state MUST ship with an UpgradeStep, or a proven no-op, plus a golden-fixture
load test. No exceptions, no "later".**

Saved state means any of: a `[Save]` component or buffer (a field added, removed, retyped,
reordered, or moved into padding, which changes the StableTypeHash with no size change); a new
`[Save]` type; `Parent`/`LocalTransform`; `SaveState`/`SaveMetaState` fields; an
`ISerializableSystem` payload; a config asset name or id a save refers to (items, techs, recipes);
an entity whose saved layout changes; a network operation whose effect persists. An Entities
package upgrade counts too: it can shift every StableTypeHash.

**Compatibility covers saves from the current master version (the public build) and every beta
since.** The golden fixtures are how that is proven: `Assets/Tests/Serialization/Fixtures/`
(slate and rules in its README; `MasterNewGame-0.21.0.34` is the master save).

**Why:** 0.50.0.45 shipped to players unable to load any save from 0.50.0.35 to .44.
Commit `1f0f1b62f` appended `Player.SimulationVelocity` (200 -> 224 bytes) and moved
`PlayerAbilityFireIntent.LeadMilliseconds` into tail padding (same size, new StableTypeHash), with
no step. Its message assumed old saves would "zero-extend". They took the columnar fast path, and
`ColumnarFastPathLoader.ValidateComponentLayouts` refused them ("'FFComponents.Player.Player' was
200 bytes at save time but is 224 bytes now"). #529 (`ResearchBotPhysicalState`, 0.50.0.17) was
the same failure. The golden-fixture test was green both times: its decode skipped that guard.
Fixed in 0.50.0.46 by `Step0_50_0_45PlayerSimulationVelocity`.

**How to apply:**
- **Plan**: every `specs/NNN-*/plan.md` has a `## Save compatibility` section (template in
  `.specify/templates/plan-template.md`): the saved state touched (or "none" plus the search that
  proves it), the upgrade step, and the loads to prove. `speckit-plan` writes it;
  `speckit-implement` fails review without it.
- **Step**: version it at the NEXT release (`FFVersion.FinalFactoryVersion` with rc + 1). A layout
  change needs `RequiresEntityDictionary => true` and an `Upgrade()` that rewrites the old bytes
  (`Step0_50_0_45PlayerSimulationVelocity` is the pattern for an appended field;
  `feedback-upgrade-steps-over-fast-loads` for why slow once is fine). A step versioned above the
  build re-runs on every load until the version bump, so a data-changing step is idempotent or
  flag-guarded (the `SaveState.ChargeIsStoredEnergy` pattern; `built-pair-lab-traps-2026-09-27`).
  **A step goes stale while its PR waits**: it runs only on saves stamped below its version, so a
  release that ships first stamps its saves at or above it and they are skipped. Before the merge,
  and again before a bump, re-version any step added since the last release above that release, and
  test a save at the last release's version (67043c1ff moved w393 to .77; a53d8acdb moved w455 from
  .80 to .82 after two releases shipped).
- **Tests** (all exist on develop since 0.50.0.46):
  - `SaveLayoutSnapshotTest` (fast suite) fails on any saved-layout change. Fix it by adding the
    step, then regenerate via `Final Factory/Serialization/Regenerate Save Layout Snapshot`; the
    menu refuses a change no newer dictionary step covers. Never hand-edit
    `SaveLayoutSnapshot.json`.
  - `GoldenSaveFixtureTests` (fast suite) decodes every fixture through the real chain and runs
    the fast path's layout guard on `columnar-fast` ones.
  - `SaveCompatibilityLiveLoadTest` (PlayMode) loads master's and each beta's fixture into a live
    world. Run it for any saved-state change.
  - A proven no-op means those three are green with no step, and the plan says why.
- **New layout generation = new fixture**: when a step pulls the newest fast-path fixture off the
  fast path, mint one from a project-owned save written at or above it (README Rule 4: no player
  saves without consent; confirm every SteamId in it). Add it to the slate and to
  `SaveCompatibilityLiveLoadTest.Fixtures`.
- **Release**: the release run's own `Test in editmode` gate runs `GoldenSaveFixtureTests` and
  `SaveLayoutSnapshotTest` and blocks the upload if they fail; `ci-release` runs no local precheck
  (Lothsahn, 2026-09-28). CI runs EditMode only, so `SaveCompatibilityLiveLoadTest` is not in it.
- **Load failures**: any exception in a load must end at the main menu with the localized "Could
  Not Load Save" dialog naming the reason (`SaveGameManager.HandleLoadFailure`,
  `SaveLoadFailureReturnsToMenuTest`). Never start a load child with `StartCoroutine`: step it
  inline (`SaveLoadGuardTest` checks the source).
