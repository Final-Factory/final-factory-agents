---
name: a-release-lands-where-setlive-says
description: "Where a release goes live is ffbox's SETLIVE table, read from ffbox's code or by scripts/release-status.py, never recalled: since w1137 (2026-10-12) a version bump merged into master lands on development and nothing sets pre-release or the default branch. Never propose moving a Steam branch by hand while the script says BUILDING or WAITING."
date: 2026-10-03
---

# A release lands where SETLIVE says

**Rule.** Before saying where a release is, or what must happen for it to reach players, run
`python scripts/release-status.py <version>` in the game repo. It reads ffbox's own
`scripts/release_lane.py` `SETLIVE` table and each Steam branch's BuildID. Report the branch it
LANDED on. Never recall the rule from a skill, a report or a person's memory, and never propose a
hand change to a Steam branch while the script says BUILDING or WAITING.

**Why.** `SETLIVE` is code its owner can change, and every prose copy of it (a skill, a script
comment, a person's memory) drifts. On 2026-10-02 a release driver reported two landed builds as
needing a hand move to another branch, the notes worker waited for that branch and skipped both
posts, and an orchestrator then planned to move the next build from Ben's Chrome through Steamworks.
Ben, the same day: "you should be doing builds from ffbox and it does upload to steam [...]. we've done
it a million times, how can we make you not confused about this anymore? hooks? a script?" Earlier,
0.50.0.62 had been reported as stuck when it was slow: it landed 72 min after the bump, inside the
measured range.

**How to apply.**

- Starting, following or reporting a release: `release-status.py`. Its verdict is the status:
  BUILDING and WAITING are normal (measured 22-78 min from the bump, median 36); LANDED names the
  branch and BuildID; LATE (over 60 min after the Release jobs end) is a question for the ffbox owner;
  NOT UPLOADED means a test job failed.
- Notes go out for the branch the build LANDED on (`ci-release`, `patch-notes.md`).
- Since w1137 (2026-10-12; ffbox 8fbb8d5) `SETLIVE = {("master", "main"): ("development",)}`: a version
  bump merged into master is a dev build and lands on `development`, which tracks master's tip. `develop`
  is in `RETIRED_BRANCHES` and a bump there builds nothing. Ben: "keep development steam branch at the
  tip of master until we are ready to release a batch of updates into main"; Lothsahn: "have pre-release
  and default be manual tags".
- `pre-release`, the default (public) branch, or any branch `SETLIVE` does not name, is Ben's or
  Lothsahn's partner-site move; nothing sets them, and an agent never sets, moves or plans one. Say so
  once, as a choice; don't do it and don't keep asking.
- If ffbox's `SETLIVE` changes, the script follows it by itself; fix the prose here and in
  `ci-release` in the same change.
