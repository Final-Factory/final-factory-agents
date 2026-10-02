---
name: no-merge-before-the-review
description: "A change merges after its verification is finished, not while a review, a clip or an audit is still pending. Unfinished evidence goes under Not verified and out of the title."
date: 2026-10-02
---

# No merge before the review

**Rule.** If the pull request says a review, a clip, an audit or a test run is pending, it is not
ready to merge. Finish it, or take the claim it would support out of the title and list it under
"Not verified".

**Why.** On 2026-10-02 the quick-craft fix (#913) merged 37 minutes after it opened. Its own
description said "The `watch_video` review is pending on BEAST". The day before, the miner
explosion fix (#886) merged 39 minutes after it opened on editor-rig evidence, with the built
game never looked at; it shipped in 0.50.0.64, where Ben found the explosion still huge. Workers
are trusted to integrate verified work on their own, and that trust is the reason "verified" has
to mean finished.

**How to apply.**

- Before merging, run `pr_evidence.py` on the pull request ([the merge checklist](../checklists/merge.md)).
  It fails on anything pending in the `## Evidence` section, and `--comment` leaves the verdict
  on the pull request before the merge.
- If the review cannot run where you are (no key on this machine, no built player), move the work
  to where it can, or hold the pull request and say what is missing and when it will merge. Don't
  merge and promise the review afterwards.
- The other half of this rule: once the review is finished and CI is green, merge it yourself.
  An open, green pull request with no stated reason is unfinished
  ([merge your own pull request](merge-your-own-pr.md)).
- Speed is not a reason. A merged change that is wrong costs a release and a report from a
  player.
