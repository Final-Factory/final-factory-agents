---
name: mirror-implementation-golden-fixture
description: Mirror implementations of the same logic in different languages (C#/shell/python) need a shared golden fixture plus a test that all mirrors agree
metadata:
  type: project
---

When the same logic is deliberately reimplemented in more than one language — e.g. a C# report-
only verdict set mirrored by a shell or Python audit-tooling equivalent — the mirrors WILL drift
silently unless something forces them to agree. A code review catching "these look equivalent" is
not enough; subtle semantic differences (rounding, ordering, an edge case one mirror forgot) only
surface as a real divergence much later.

**How to apply:** whenever you add or touch a mirrored implementation, pin one golden fixture
(input → expected output) in EVERY mirror, and add a test that runs all mirrors against it and
asserts they agree with each other, not just with a hand-picked expected value. Add the new
mirror's fixture in the same change that adds the mirror — never "will add the cross-check
later".
