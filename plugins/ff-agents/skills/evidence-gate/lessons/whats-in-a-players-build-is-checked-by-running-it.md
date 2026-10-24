---
name: whats-in-a-players-build-is-checked-by-running-it
description: "A claim that a player-facing feature or fix is, or isn't, in a build players run (a Steam branch, a build number) rests on running that build, or a build of its exact commit, and opening the feature; a code grep or git ancestry is a guess that names the build to run. Asked to investigate, investigate: a doubt a quick look leaves is settled by the run (an orchestrator files it in the same turn). A DONE for a player-facing fix names the Steam branch and build that carry it and whether pre-1.0 needs a cherry-pick. Where a release lands is read from release-status.py (SETLIVE), never recalled."
date: 2026-10-22
---

# What is in a player's build is checked by running it

**Rule.** "Feature X is in build Y" and "players on branch Z have it" (or don't) are claims about what a player sees, so
they rest on what a player would run:

- **The basis is a run.** Run that build, or a player built from the exact commit that build was made from, and open the
  feature (the screen, the tab, the button). Say what you ran (the Steam branch and BuildID, or the commit and the
  player's path) and what you saw. A code grep, `git merge-base --is-ancestor`, a branch's file list or a past report
  say what a commit holds, not what a player's game shows: the build may come from another commit, a toggle may hide
  the feature, the branch may serve an older BuildID, the player may run a cached install.
- **Without the run it is a guess, labelled so, naming the build to run**: "guess (from git): Build 111 contains #1760;
  to check, run Build 111 from pre-release and open Load". A guess is never passed on as a finding, and an orchestrator
  never turns a worker's git check into "players have it".
- **Asked to investigate, investigate.** When a person asks you to investigate, find out what happened or why players
  don't see something, a quick look (a grep, git, a past report) is where you start, not the answer. If it leaves any
  doubt about what players see, run the check yourself before answering; an orchestrator, which cannot run a build,
  files the reproduce work (`request_work`) in the same turn and tells the person what it filed and what its quick look
  rests on. Never a confident explanation built on the quick look.
- **A DONE for a player-facing fix says where it ships.** The report names the Steam branch and build that carry the
  fix, or the bump that will ("development, Build 112 (1.0.0.112); no pre-release or default build has it"), and says
  whether the pre-1.0 line needs a cherry-pick: master is the 1.0 build on the Steam `development` branch; `pre-1.0` is
  the hotfix line the default branch's builds come from until 1.0 ships. A fix players on the default branch asked for
  that lands only on master has not reached them.

**Why.** Two corrections from Ben on 2026-10-22, both about the Load screen's Saves and Autosaves tabs (w1315, PR #1760,
merged to master 2026-10-14):

1. The fix was reported done on master without saying that it reaches only the 1.0 build. A week later Ben: "it looks
   like it's not in the game yet, and I asked you to do this like a week ago, and players are complaining about it on
   the Discord forum. What happened? Why didn't you do this?"
2. Asked to find out what happened, his orchestrator told him the 1.0 development build "still has the tabs" from a code
   grep, and w1765's worker closed the request with "pre-1.0 and Build 111 already contain the tabs and filter (#1760)
   ... checked with git". Ben: "My playtesters who are all on the 1.0 development branch are saying it's not there, so
   you're lying to me, or you didn't actually check." Then: "I mean, you can check the code, but it just seems like you
   didn't investigate at all. Like, if you're unsure, then do the check. Like, I told you to investigate it. Like, it
   seems like a harness issue here." Nothing was filed to reproduce it until he pushed back (w1769 now looks for the
   real cause).

Earlier, 2026-10-02: a release driver recalled where builds land, reported two landed builds as needing a hand move to
another branch, and an orchestrator planned to move the next one from Ben's Chrome. Ben: "you should be doing builds
from ffbox and it does upload to steam [...]. we've done it a million times, how can we make you not confused about this
anymore? hooks? a script?" (the section below).

**How to apply.**

- Before writing "in", "has", "contains", "missing" or "not in" next to a build number, a version or a Steam branch:
  either you ran it (say so, labelled measured, with what you opened) or the sentence says guess and names the build to
  run. `python "$FF_SKILLS/evidence-gate/build_claim_check.py" <report>` (this skill) flags a build claim that carries neither, and `--done` checks
  a player-facing fix's `Ships in:` and `pre-1.0:` lines.
- Which build a branch serves and which commit made it: `python scripts/release-status.py [<version>]` in the game repo
  (each Steam branch's BuildID, the version's bump commit). Then run that build, or build that commit in the slot pool
  (`player_slots.py launch`), with the person's kind of save if the feature needs one, and open the feature.
- A player-facing fix's DONE: `Ships in: <branch>, <build or "the next master bump">` and `pre-1.0: cherry-pick needed
  (<wNNN or PR>)` or `pre-1.0: not needed: <why>`. If players on the default branch reported it, "not needed" needs its
  reason in their terms (the default branch moves to 1.0 before they'd get a hotfix, or the person said so).

## Where a release lands is read, not recalled (2026-10-03)

**Rule.** Before saying where a release is, or what must happen for it to reach players, run
`python scripts/release-status.py <version>` in the game repo. It reads ffbox's own `scripts/release_lane.py` `SETLIVE`
table and each Steam branch's BuildID. Report the branch it LANDED on. Never recall the rule from a skill, a report or a
person's memory, and never propose a hand change to a Steam branch while the script says BUILDING or WAITING.

**Why.** `SETLIVE` is code its owner can change, and every prose copy of it (a skill, a script comment, a person's
memory) drifts. On 2026-10-02 the notes worker waited for the wrong branch and skipped both posts. Earlier, 0.50.0.62 had
been reported as stuck when it was slow: it landed 72 min after the bump, inside the measured range.

**How to apply.**

- Starting, following or reporting a release: `release-status.py`. Its verdict is the status: BUILDING and WAITING are
  normal (measured 22-78 min from the bump, median 36); LANDED names the branch and BuildID; LATE (over 60 min after the
  Release jobs end) is a question for the ffbox owner; NOT UPLOADED means a test job failed.
- Notes go out for the branch the build LANDED on (`ci-release`, `patch-notes.md`).
- Since w1137 (2026-10-12; ffbox 8fbb8d5) `SETLIVE = {("master", "main"): ("development",)}`: a version bump merged into
  master is a dev build and lands on `development`, which tracks master's tip. `develop` is in `RETIRED_BRANCHES` and a
  bump there builds nothing. A `pre-1.0` bump uploads both apps and sets nothing live (w1436). Ben: "keep development
  steam branch at the tip of master until we are ready to release a batch of updates into main"; Lothsahn: "have
  pre-release and default be manual tags".
- `pre-release`, the default (public) branch, or any branch `SETLIVE` does not name, is Ben's or Lothsahn's partner-site
  move; nothing sets them, and an agent never sets, moves or plans one. Say so once, as a choice; don't do it and don't
  keep asking.
- If ffbox's `SETLIVE` changes, the script follows it by itself; fix the prose here and in `ci-release` in the same
  change.
