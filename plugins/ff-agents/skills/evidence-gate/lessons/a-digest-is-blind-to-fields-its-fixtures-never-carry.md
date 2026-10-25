---
name: a-digest-is-blind-to-fields-its-fixtures-never-carry
description: "A regression digest over checked-in fixtures proves nothing about a field the fixtures never set, or one the digest leaves out. Assert every excluded field's value; for an old-file check, write the fixture with the old tree's own serializer and read it at HEAD, with mutant arms; turn on the feature toggle the path reads, or both arms agree without running it (w2124, 2026-10-25)."
date: 2026-10-25
---

# A digest is blind to fields its fixtures never carry

**Rule.** A digest test that hashes what a set of checked-in fixtures convert to, and that a
change re-pins, only shows that the fixtures still convert the same. It shows nothing about a field
none of the fixtures set, and nothing about a field the digest leaves out. Before you call a re-pin
safe:

1. **Assert every field the digest excludes.** Don't drop a field from the hash and move on. Assert
   its value for every fixture: empty, zero, or equal to the old field it replaced.
2. **List what the fixtures never carry.** For each feature the change touches (a circuit, a filter
   mode, a nested blueprint), check that some fixture actually sets it. Where none does, write a
   fixture that does.
3. **Write an old-file fixture with the old tree's own serializer**, never by hand. Restore the
   parent's scripts and tests (`git restore --source=<parent> -- Assets/Scripts Assets/Tests`) in a
   scratch worktree, run a scratch writer test that saves the file the way the game saved it then,
   copy the file out, and read it at HEAD the way the game reads it (the library loader, not a bare
   JSON parse).
4. **Give it mutant arms.** Break each gate or attach step the fixture relies on and watch the test
   go red. A test that stays green with the code it guards removed proves nothing.
5. **Turn on the feature toggle the path reads.** With the toggle off, the code under test returns
   early. Both A/B arms then agree, and the agreement shows nothing.

**Why.** w2124 (2026-10-25), the nightly regression check of blueprint and circuit copy. Three PRs
had re-pinned `BlueprintPasteBefore2334DigestTest`: #2461 (connector circuit filters), #2369
(station stop circuits) and #2464 (the Combat filter option). Each one either added its new fields
as defaults or left them out of the hash. The field-by-field dump at each merge was clean. But no
`ValidationScenarios` string carried a circuit, an Intermediates filter or a projector copy, so
the digest had never seen the cases those PRs changed. A 1.0.0.15 library file written by that
tree's serializer and read at HEAD was what pinned them (`BlueprintOldLibraryFilePasteTest`).
Mutant arms went red for each case: the Combat gate moved to 1.0.0.15, `BlueprintStopCircuits.Attach`
removed, `BlueprintProjectors.Attach` removed. Every paste A/B ran under
`FeatureToggles.OverrideScope(FeatureToggles.Circuits, true)`, because with Circuits off
`BlueprintCircuits.Attach` returns before it reads anything.

**How to apply.** In a regression check's verdict table, the digest row says what the fixtures
don't carry ("Gap: no fixture has X; pinned by <test>"). The PR's Tests line names the excluded
fields it asserts and the mutant arms that went red.
