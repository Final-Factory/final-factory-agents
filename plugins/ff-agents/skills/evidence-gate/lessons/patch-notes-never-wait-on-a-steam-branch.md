---
name: patch-notes-never-wait-on-a-steam-branch
description: "A release's patch notes post once, as Max in #dev-patch-notes, as soon as the build is live on Steam: LANDED on the branch the lane sets, development included (a pre-1.0 hotfix, set live nowhere: BUILT). Never hold them until someone moves the build to pre-release or default, never ask a person which branch, and never offer 'leave it on development' as an answer that means no notes. The first crash, desync and hang check counts from the landing time. Two release workers did it on 2026-10-28 (w2431, w2440) and lothsahn corrected both; FF Factory's waiting_on_person now refuses a Steam branch card (ff-factory #740)."
date: 2026-10-28
---

# The patch notes never wait on a Steam branch

**Rule.** "Live on Steam" means landed on the branch the release lane sets: `development` for a master bump
(`release-status.py` says LANDED), the upload itself for a pre-1.0 hotfix, which the lane sets live nowhere (BUILT).
The notes post then, once, as Max in #dev-patch-notes. Where the build goes next (`pre-release`, the default branch) is
Ben's or Lothsahn's own move on the partner site, in their own time. It is never a step of the release, never a
precondition for the notes, and never the subject of a question. The first check (crash, desync and hang reports by
signature against the previous build) counts from the landing time.

**Why.** On 2026-10-28 two release workers held their notes behind a branch card, and lothsahn corrected both:

- w2431 (0.50 Build 113, a pre-1.0 hotfix): its card asked Ben and lothsahn to "Set Build 113 ... on pre-release, test
  it, then set it live on default", and said the notes would follow. lothsahn: "Add the patch notes now. I'll update it
  later. Close the workitem".
- w2440 (1.0 Build 22, live on development as BuildID 26260109): its card asked them to "Choose a Steam branch for 1.0
  Build 22", where leaving it on development meant no notes. lothsahn: "It's a dev build but you still upload the patch
  notes. Why did you suddenly decide not to update patch notes for development builds. We've done that for ages".

Both briefs, written by the dispatcher, said "post the patch notes ... when the build is live on default" and timed the
first check "24 h after it reaches default". The skill gave them that reading: `patch-notes.md` said "A post that says
'pre-release' or 'default branch' waits for one of them to say it is there", and `pre-1.0-hotfix.md` said to ask for the
default move with `waiting_on_person` and to post "once default carries it". It is the second miss of this kind:
0.50.0.65 and .66 went unposted on 2026-10-02 because a worker waited for a branch ffbox does not set
([a release is done when its notes are posted](a-release-is-done-when-its-notes-are-posted.md)).

**How to apply.**

- At LANDED (or BUILT for a pre-1.0 hotfix), post with `post_as_max` before anything else, then report the BuildIDs and
  where it landed. A brief that says "once live on default" is wrong on this point: post on landing and say so.
- Before sending any card or report that names `pre-release` or the default branch, check: does it ask which branch,
  or hold the notes until one? Then it is wrong. Report where the build is; never ask.
- Time the first check, and any 24-hour signature comparison, from the landing.
- The check: FF Factory's `waiting_on_person` refuses a card that asks a person to choose, set or move a Steam branch
  (`shared/releaseBranchAsk.ts`, ff-factory #740, with these two cards as fixtures), and `read_rules release` tells the
  dispatcher to write "once it is live on Steam". The ci-release skill's section 3 checklist and the evidence-gate
  `checklists/release.md` item 9 carry the line.
