---
name: a-release-after-work-items-builds-on-the-tip
description: "A release asked for after one or more work items ('release when w1 and w2 are done') gets no A-or-B card: it waits for those items, then bumps on master's tip. Ask the person only if one of them closes without a merged change. Every other release keeps the card."
date: 2026-10-29
---

# A release after work items builds on master's tip, with no A-or-B card

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
