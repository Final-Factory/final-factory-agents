---
name: a-save-version-bump-that-keeps-old-saves-loading-needs-no-person
description: "A save-format version bump (a section version, an UpgradeStep, a layout change) merges without a person when old saves still load, proved by a test that loads a save from before the bump. A newer save refused by an older build with the clean 'newer version' error is fine. Only a change that breaks loading existing saves goes to a person."
date: 2026-10-23
---

# A save-format bump that keeps old saves loading needs no person

**Rule** (Ben, 2026-10-23, w1826, on FFBox's Leech belt-target fix that took the belt section from
version 2 to 3: "its fine that a later version save doesnt load in an old version of the game lol.
just backwards compatibility is important"):

- **Backwards compatibility is the gate; forwards compatibility is not.** A save written by a newer
  build that an older build refuses, with the clean "newer version" error, is acceptable and needs
  no one's say-so.
- **A version bump that keeps old saves loading merges without a person.** Proof: a test that loads
  a save written *before* the bump (a golden fixture minted on the old code, or an old-format
  payload built by the test) through the real load chain, with the upgrade step or reader running,
  and asserts the loaded state. `GoldenSaveFixtureTests`, `SaveLayoutSnapshotTest` and the PR's
  own old-save test are green, the plan or PR's `Save compatibility` section names them, and the
  merge follows the usual verification and green CI ([merge your own PR](merge-your-own-pr.md)).
- **A change that breaks loading existing saves still goes to a person**: a saved layout or id
  change with no step or no old-save test, a step that drops or rewrites player data, a fixture
  that no longer loads. Hold it, say which, and declare the wait (`waiting_on_person`).
- Rules kept for other reasons stay: the hard rule that saved state ships an UpgradeStep (or a
  proven no-op) plus a golden-fixture test
  ([save-compatibility-hard-rule](../../project-memory/memories/save-compatibility-hard-rule.md)),
  the crown-jewel surfaces, a failing-first test and the two-peer check for a class 2 desync fix.
  What this lesson removes is only the stop to ask a person for the bump itself.

**Why.** w1826 stopped at an open, green PR for hours to ask Ben and Lothsahn whether a belt
section version bump was allowed, though old saves loaded. The answer was yes, with the sentence above.

**How to apply.** Before asking about a save-format change, check that an old-save load test is in
the diff and ran green. Present: no question, merge on the usual gates. Missing: write it first
(that is the work, not a question). Present but red, or the change cannot keep old saves loading:
ask.
