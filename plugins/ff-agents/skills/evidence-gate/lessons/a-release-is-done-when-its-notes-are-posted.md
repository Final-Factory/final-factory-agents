---
name: a-release-is-done-when-its-notes-are-posted
description: "A requested release is done only when release-status.py says LANDED on development (a master bump; pre-release and the default branch are a person's move) AND its patch notes are posted once, as Max, in #dev-patch-notes, with post_as_max (any machine; FFBox posts). A failed post is reported as an open step with FFBox's reason instead of finishing. The notes cover only what a player sees and feels (features, fixes, balance, performance, platform support) and never git branches, the dev flow, CI, the merge queue, FFBox, agents, workers or PRs: release_notes_lint.py (game repo) runs before the bump and before post_as_max (Build 101, w1190). Every notes line is also something a release player can get: a change behind a feature toggle (every toggle is off for a release player; Build 104's 'Mobile stations take their bots and barges with them', w1242) never ships, and release_notes_check.py (evidence-gate) runs with the lint, before the bump and before post_as_max."
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
  owner decides (checklist: `checklists/release.md` item 2b). The same day Build 104's draft listed a change
  behind a feature toggle: see the last section (`release_notes_check.py`, which also runs this lint).
- An orchestrator that dispatches a release puts "post the patch notes once live" in the brief, and
  does not close the release until the link is in.

## Patch notes list only what players can use (Build 104, w1242)

**Rule.** Every line in the notes passes two tests before the bump and again before `post_as_max`:

1. **A release player can get it.** A release player starts with every feature toggle off
   (`Documentation/Feature-Toggles.md`, "Release player (every Steam branch): every toggle off"), so a change
   whose code or content sits behind a toggle that is still declared in `FeatureToggles.cs` at the release
   commit is not in the build players run, whatever its developer default. It is not a note.
2. **It is not our workflow.** No git branches, dev flow, CI, merge queue, FF Factory, FFBox, agents,
   workers or PRs.

`python "$FF_SKILLS/evidence-gate/release_notes_check.py" <notes> --repo <game clone> --range <previous release sha>..<release sha>` (beside
`pr_evidence.py` in the `evidence-gate` skill) checks both. Exit 0 before the bump and before the post.

**Why.** Ben corrected the same family of mistake twice on 2026-10-13:

- Build 101 (w1190): the notes told players that dev builds now come from master. Ben: "please dont put that
  kind of specific workflow information in patch notes for users. like what the hell man? please remember
  this". `release_notes_lint.py` (game repo) was the first fix; it only knows words.
- Build 104 (w1242): the draft listed "Mobile stations take their bots and barges with them" (w243, PR #1666).
  That change ships behind the `inserters-ride-stations` toggle, off by default (`FeatureToggles.cs`). Ben:
  "Mobile stations take their bots and barges with them / Isnt this behind a feature toggle?" The brief's
  list of merged PRs did not say which of them were toggled, and the lint cannot see a toggle: the line has no
  forbidden word. Nothing in the process checked it, so a person did.

**How to apply.**

- Run the check on the draft with the range the notes cover (`patch-notes.md` section 1 finds the previous
  release sha; the release sha is origin's tip plus the bump, or the bump commit once it exists):

  ```sh
  CHECK=$(ls -d ~/.claude/plugins/cache/final-factory-agents/ff-agents/*/skills/evidence-gate/release_notes_check.py | sort -V | tail -1)
  python "$CHECK" Temp/release-notes-<version>.md --repo . --range <previous release sha>..origin/master
  ```

  It lists the toggles live at the release commit and the merged PRs that declare or use one, then fails on a
  bullet that matches one of those PRs (its number or request id, or words it shares with the PR's commit
  subjects and the toggle's description) and on every workflow word the game repo's lint knows.
- A hit is a prompt to look, not a verdict. Read the PR: a line about a toggled feature comes out. A mixed PR
  (an ungated fix beside gated work) keeps a line reworded to only the ungated part, and you pass
  `--accept <PR>`; say in the release report which PR and why.
- The matching is words, so a heavily paraphrased line can slip past it. The list of toggled PRs it prints is
  the second half of the check: read each of them against the notes once, and tell whoever asked for the
  release when a toggled PR was left out on purpose.
- A toggle that was removed in the range (the PR shipped it) is not toggled any more: its PRs are fine. The
  check reads that from `FeatureToggles.cs` at the previous release against the release commit.
- A toggled change reaches the notes only when the release turns the toggle on (a release that clears the
  gate). Then the PR that clears it is the one the note comes from.
- Dry run (w1264, Build 104's range `57ba88a0ee..fd84b38630`, game repo): the draft with the w243 line fails
  with `matches PR #1666 ... behind toggle inserters-ride-stations`, and the other 28 bullets of the committed
  notes pass. Test: `tests/test_release_notes_check.py` (Build 101's line and Build 104's line are both
  fixtures).

## The notes never wait on a Steam branch (w2431, w2440)
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
(this lesson, above).

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

## A release after work items has no A-or-B card (w2536)

**Rule** (lothsahn, 2026-10-29, w2536: "If someone asks for a release after a workitem or set of work items, always
build off the tip when those work items merge."). When a release is requested to follow one or more work items
("release when w1 and w2 are done"), there is no A-or-B card:

- The release request is blocked on those items (`blocked_on` with their pull requests).
- Once they have merged, it bumps on master's tip (A).
- If one of those items closes without a merged change, the person is asked (`waiting_on_person`) before the release
  goes ahead.
- Every other release request keeps the A-or-B card as today (`ci-release` section 1, `urgent-release.md` section 0).

**Why.** lothsahn: "Because they need to have those there." The card's B is the last fully green commit
(`scripts/release/last_green.py`), which is older than the merges the person waited for, so B can leave the requested
work items out of the release. The rule came with w2535 (a normal release from master's tip once the crash fixes w2533
and w2534 merged).

**How to apply.** Before you bring the A-or-B card, read the release request and its notes: does it name work items,
pull requests or fixes the release must carry ("after", "once", "when ... are done", "with the fix for")? Then there is
no card. Declare the wait with `blocked_on`; when you are resumed, check each item merged (`gh pr view <n> --json
state,mergeCommit`), confirm the merge commits are on `origin/master`, and bump with `trigger-ci-release.sh` (no
`--from green`). The release checklist's "Before the bump" has the line.
