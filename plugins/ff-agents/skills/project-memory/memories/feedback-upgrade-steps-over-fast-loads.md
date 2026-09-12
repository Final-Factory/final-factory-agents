---
name: feedback-upgrade-steps-over-fast-loads
description: Ben 2026-09-12 — a real save-format change gets a real upgrade step (RequiresEntityDictionary true, slow load for older saves); fast loads only matter when the save's version matches the running build
metadata:
  type: feedback
---

When a `[Save]` component's layout genuinely changes (a field added, removed, or retyped), write
the `UpgradeStep` the straightforward way. Declare `RequiresEntityDictionary => true` and widen or
rewrite the blob in `Upgrade()`, following `Step0_21_0_12InserterRange`. Older columnar saves then
take the dictionary-materialized path once. **Just do it.** Don't design content-aware
path predicates or other machinery just to keep older saves on the columnar fast path.

**Why:** Ben, 2026-09-12: "if there's a real upgrade change, we just want to do it. We only care
about fast loads when the version doesn't change." A save one version behind loads slowly once,
and every save written afterwards is back on the fast path. The trigger was #529: it appended
`ResearchBotPhysicalState.Origin` (80 → 104 bytes) but declared its step
`RequiresEntityDictionary => false`, so older saves stayed on the fast path. There
`ColumnarFastPathLoader.ValidateComponentLayouts` refused them ("was 80 bytes at save time but is
104 bytes now") and every pre-0.50.0.17 save with research bots failed to load.

**How to apply:**
- A step that only does `PostLoadUpgrade` work on unchanged layouts keeps `=> false`. A step for a
  changed layout needs `=> true`. Getting that wrong means refused loads, not slow ones.
- The invariant worth protecting is narrower: a save stamped with the running build's own version
  must never need the dictionary (see `Step0_50_0_9RangeSplitTest`).
- Expect the golden save fixtures to move. Manifests below the new step go from `columnar-fast` to
  `dictionary-materialized`. If that leaves no fast-path fixture,
  `GoldenSaveFixtureTests.BothColumnarLoadPathsHaveAFixture` fails. Fix it by minting a fixture from
  a project-owned save written at or above the step (confirm every player in it with Ben first, since
  SteamIds become permanent git history), not by weakening the step.
