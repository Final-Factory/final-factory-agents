---
name: a-release-is-done-when-its-notes-are-posted
description: "A requested release is done only when release-status.py says LANDED on development (a master bump; pre-release and the default branch are a person's move) AND its patch notes are posted once, as Max, in #dev-patch-notes, with post_as_max (any machine; FFBox posts). A failed post is reported as an open step with FFBox's reason instead of finishing. The notes cover only what a player sees and feels (features, fixes, balance, performance, platform support) and never git branches, the dev flow, CI, the merge queue, FFBox, agents, workers or PRs: release_notes_lint.py (game repo) runs before the bump and before post_as_max (Build 101, w1190)."
date: 2026-10-13
---

# A release is done when its notes are posted

**Rule.** Every requested release (a version bump merged into master) ends with two checks, and is
not reported done until both hold:

1. it is live on its Steam branch: `python scripts/release-status.py <version>` says LANDED, on
   `development` (the one branch ffbox sets; since w1137 develop is retired);
2. its patch notes (`cicd/release-notes/<version>.md`, player-facing, no internal ids) are posted
   once, as Max, in #dev-patch-notes, and the report carries the message link.

**Why.** Lothsahn, 2026-10-03: "any time a release is requested, you should always post the
#dev-patch-notes after the build is complete and uploaded." On 2026-10-02 the notes for 0.50.0.65
and .66 were never posted: the worker waited for a Steam branch ffbox does not set and finished
without them, and nothing in its report said the post was missing.

**How to apply.**

- Treat the post as the release's last step, in the `ci-release` checklist (section 3), not as a
  courtesy after the report.
- Post with `mcp__machine__post_as_max` from any machine (w901, 2026-10-10: Lothsahn, "at some point,
  a worker on LothDesktop didn't have access to publish the notes. Please make sure that workers can
  request FFBox send a discord message"). FFBox holds the bot; `ci-release` `patch-notes.md` section 4
  has the call (`channel: dev_patch_notes`, `file`, `skip_lines: 2`, `key: <version>`). If it fails,
  report "live on <branch> (BuildID …), patch notes NOT posted: <FFBox's reason>" with the notes
  file's path, and leave the step open. There is no "no config on this machine" excuse any more.
- **Patch notes are for players** (Ben, 2026-10-13, w1190). Build 101's notes said "from master, the new
  trunk" in the Steam description, "From Master" in the title and "Dev builds now come from master: every
  change lands there first, and the development branch follows it." in the body, the day develop was retired
  (w1137). Ben: "please dont put that kind of specific workflow information in patch notes for users. like
  what the hell man? please remember this". The notes say only what a player sees and feels: features,
  fixes, balance, performance, platform support. Never git branches (master, develop), the dev or branching
  flow, CI, tests, the merge queue, FF Factory, FFBox, agents, workers, PRs, or which Steam branch follows
  which git branch. Only the standard `(Live on the development branch)` title and `Restart Steam to pick up
  the update on the development branch.` line name a branch, because players need to find the build. A change
  to how we work is not a note, even when it is the biggest change in the range.
  Check it mechanically, not by eye: `python scripts/release_notes_lint.py <notes>` (game repo; whole-word,
  case-insensitive; fails on master, develop, branch outside those two lines, CI, merge queue, pull request,
  PR, worker, agent, FF Factory, FFBox, workflow, git, request ids). `trigger-ci-release.sh --notes` runs it
  before the bump; run it on the committed copy before `post_as_max`. A hit is reworded, not argued with, and
  a clean lint is a floor, not a judgment. The posted message is public: no agent edits or reposts it, the
  owner decides (checklist: `checklists/release.md` item 2b).
- An orchestrator that dispatches a release puts "post the patch notes once live" in the brief, and
  does not close the release until the link is in.
