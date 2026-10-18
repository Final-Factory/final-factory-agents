---
name: ask-before-content-goes-live
description: "Before a build makes major new content live on any Steam branch (1.0, a feature toggle turned on by default, an open beta), stop and ask the person for the go-live moment, even when a plan they agreed says the content goes there. A plan is where it goes, not when. Routine hotfix builds don't need it."
date: 2026-10-18
---

# Ask for the go-live moment before big content reaches a Steam branch

**Rule.** Before a build that makes major new content live on any Steam branch (`development`
included), the worker stops and asks the person who owns the release for the moment it goes live
(`mcp__machine__waiting_on_person`), and starts the build only on their go for that moment. This
holds even when a plan they agreed already says the content goes to that branch: a plan says
*where* content goes, never *when*. Major new content means 1.0, a feature toggle turning on by
default (a version reaching a toggle's release in `FeatureToggles.OnByDefault`, or a toggle
shipped), an open beta, or anything else a player would call a new version of the game. A routine
build (hotfixes, small fixes and balance on a line players already have) needs no such ask.

**Why.** On 2026-10-18 Final Factory 1.0.0.0 (master with all nine 1.0 feature toggles on by
default, BuildID 26019698) went live on the Steam `development` branch through FFBox's release lane,
as w1436 (the pre-1.0 branch plan) had set up. Ben had agreed to the plan ("put 1.0 on
development"), and the worker read that as a go for the moment the first 1.0.0.0 bump built. Ben,
after it was live: "Wait I don't want 1.0 on development yet" / "You should have asked me I need to
do a steam event and stuff". He plans Steam events and marketing around when big content reaches
players, even on a beta branch, and a build that is live cannot be taken back quietly.

**How to apply.**

- **Recognise it before the bump, not after.** For any release, ask: does this build change what a
  Steam branch serves by default in a way players would notice as new? Read it from the code at the
  release commit, not from the notes: the version against `FeatureToggles.OnByDefault` (a 1.0.0.0
  bump turns every 1.0 toggle on), toggles deleted (shipped) in the range, and which branch
  `SETLIVE` sets ([a release lands where SETLIVE says](a-release-lands-where-setlive-says.md)).
- **Ask for the moment in plain words**, naming the content, the branch and what goes live with it
  ("Bumping master to 1.0.0.0 sets 1.0, with all nine 1.0 toggles on, live on development as soon
  as it builds. When should it go live?"). Then `waiting_on_person` and stop; don't bump, don't
  merge a bump PR, don't let a lane you set up do it for you.
- **A plan or branch setup that will make content live later says so.** A brief, plan or PR that
  changes what a Steam branch serves by default (a branch cut, a SETLIVE change, a version line, a
  toggle default) names the person's go-live confirmation: who confirmed the moment, in their quoted
  words, or "go-live moment not confirmed: ask before the first build" (checklist
  [release.md](../checklists/release.md) item 1b). The worker who sets the plan up writes that line
  for the worker who will cut the build.
- **"A release that is asked for is pre-approved" does not cover this.** A request for "a build"
  approves the build; it is not a go for major content unless the person said so for this build.
- **Only the person's own words count**, from the sender line
  ([name a decider only from the sender line](name-a-decider-only-from-the-sender-line.md)).
- **Never fix it by moving a branch.** If big content went live without a go, report it to the
  person with the BuildID and the previous BuildID; rolling back is their call, never a hand change
  to a Steam branch.
