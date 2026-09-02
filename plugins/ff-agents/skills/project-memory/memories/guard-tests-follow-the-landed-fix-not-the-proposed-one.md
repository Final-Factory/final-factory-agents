---
name: guard-tests-follow-the-landed-fix-not-the-proposed-one
description: A guard test proposed alongside a fix DESIGN guards that design's invariant — if a different fix lands, re-derive the guard from what actually shipped, not what was proposed
metadata:
  type: feedback
---

A guard test written alongside a proposed fix encodes that proposal's invariant, not the
underlying bug's. If a different fix lands, the guard now asserts the WRONG thing and can fail
on the fix itself.

**Real incident (055 R37).** The leg proposed a writer-side fix — "assert every post-pass
`Instantiate` writes `LocalToWorld`" — but Lothsahn landed a reader-side fix at game-repo
`7304103d6` instead, which makes writer-only-`LocalTransform` the INTENDED shape. The
writer-side guard would have failed on the fix that actually shipped. See
[[fixed-group-reads-of-localtoworld-are-frame-count-bugs]].

**How to apply.** Re-derive the guard from the fix that landed, never the one proposed — check
the guard's assertion against the merged commit before trusting it. And when a census-style
guard surfaces N unreviewed items, the census IS the deliverable: adjudicate every entry against
source before fixing anything (R37g: 24 readers → 10 exposed, 14 not, and the correct fix shape
differed per entry by whether the job writes the component it would otherwise read).
