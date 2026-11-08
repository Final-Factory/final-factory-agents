---
name: wait-for-a-kind-of-event-not-one-pr
description: "When a 'done when' needs an event of a kind (a merge to main that changes ffu-server, a deploy, a release of any build), any event of that kind counts. Before blocked_on one named pull request someone else owns, list the recent merges and workflow runs and measure from the first that qualifies; block on a pull request only when none has happened and none is due (w3424, 2026-11-08: ~10 h blocked on ffu #397 while 20+ qualifying merges deployed)."
date: 2026-11-08
---

# Wait for a kind of event, not for one pull request

**The rule.** A done-when that names a kind of event ("a merge to main that changes ffu-server has the world back within
15 minutes") is met by any event of that kind. Do not pick one pull request you happen to know of, owned by someone else,
and `blocked_on` its merge. First list what already happened:

```sh
gh run list -R <owner/repo> --workflow <wf>.yml -L 20 --json databaseId,event,headSha,conclusion,createdAt
gh api "repos/<owner/repo>/commits?sha=main&since=<when your change landed>" --jq '.[]|[.sha[0:9],.commit.committer.date,(.commit.message|split("\n")[0])]|@tsv'
```

and check each candidate's files (`gh api repos/<owner/repo>/commits/<sha> --jq '[.files[].filename]'`) for the kind.
Measure from the first that qualifies. Block only when none has happened; then block on the earliest that is due, and on
your next resume look again at everything that merged meanwhile, not only the one you named.

**Why (w3424, 2026-11-08).** FP.7's world.yml deploy needed a merge to ffu main that changes ffu-server, measured while
the Linux runners were busy. The worker blocked on Ben's ffu #397 (w3415) merging, at 18:58 on 2026-11-07. #397 then sat
in conflict; between 02:04 and 05:27 on 2026-11-08 ten world.yml push deploys ran, among them ffu #428 (crates/ffu-sim,
crates/ffu-content): merged 05:20:38Z, world job on ffu-biscuit-world at 05:20:44Z, new server's start line 05:21:08Z,
while ffu-biscuit-2 and ffu-biscuit-4 ran repeat jobs. The measurement was there for hours before anyone looked.

**How to apply.** Before every `blocked_on` with `prs` for a measurement (not for a merge your own work depends on), run
the two listings above. In the blocked_on `what`, write the kind ("any merge to main touching crates/ffu-server's
dependencies"), so the person reading the ledger sees it is not that one PR.
