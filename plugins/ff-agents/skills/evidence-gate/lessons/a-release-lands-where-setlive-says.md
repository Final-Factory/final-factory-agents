---
name: a-release-lands-where-setlive-says
description: "Where a release goes live is ffbox's SETLIVE table, read from ffbox's code or by scripts/release-status.py, never recalled: a develop release lands on pre-release, a master release on multiplayer-beta. Never propose moving a Steam branch by hand while the script says BUILDING or WAITING."
date: 2026-10-03
---

# A release lands where SETLIVE says

**Rule.** Before saying where a release is, or what must happen for it to reach players, run
`python scripts/release-status.py <version>` in the game repo. It reads ffbox's own
`scripts/release_lane.py` `SETLIVE` table and each Steam branch's BuildID. Report the branch it
LANDED on. Never recall the rule from a skill, a report or a person's memory, and never propose a
hand change to a Steam branch while the script says BUILDING or WAITING.

**Why.** The rule changed three times in five days, and every reader carried a different version:

- ffbox: a develop release's main app went live on `multiplayer-beta` from 2026-09-28 (`d46d438`);
  a master release's went there and a develop release's stopped on 2026-10-01 (`b2e99d6`); a develop
  release's went to `pre-release` on 2026-10-02 (`1f51596`).
- The `ci-release` skill still said develop goes to `multiplayer-beta`; the game repo's
  `trigger-ci-release.sh` said "uploaded to Steam with NOTHING set live"; Ben remembered develop
  builds on the beta branch.

So on 2026-10-02 a release driver reported 0.50.0.65 and .66 as "on pre-release only, a person must
set it live on multiplayer-beta", which was right about the branch but wrong about the remedy. The
notes worker waited for `multiplayer-beta` and skipped both posts. An orchestrator then planned to
set 0.50.0.67 live from Ben's Chrome through Steamworks. Ben, the same day: "you should be doing
builds from ffbox and it does upload to steam to the beta branch. we've done it a million times, how
can we make you not confused about this anymore? hooks? a script?" Earlier, 0.50.0.62 had been
reported as stuck when it was slow: it landed 72 min after the bump, inside the measured range.

**How to apply.**

- Starting, following or reporting a release: `release-status.py`. Its verdict is the status:
  BUILDING and WAITING are normal (measured 22-78 min from the bump, median 36); LANDED names the
  branch and BuildID; LATE (over 60 min after the Release jobs end) is a question for the ffbox owner;
  NOT UPLOADED means a test job failed.
- Notes go out for the branch the build LANDED on (`ci-release`, `patch-notes.md`).
- If the people want a develop build on `multiplayer-beta`, that is their partner-site move or a
  change to `SETLIVE` by ffbox's owner. Say so once, as a choice; don't do it and don't keep asking.
- When ffbox's rule changes again, the script follows it by itself; fix the prose here and in
  `ci-release` in the same change.
