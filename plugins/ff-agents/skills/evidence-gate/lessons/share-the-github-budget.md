---
name: share-the-github-budget
description: "Every agent, the portal and some of Ben's work spend ONE GitHub REST budget (5,000 calls an hour on Lothsahn's account, user 10092359). A history survey that makes one REST call per run or per job log, 8 at a time, spends it in minutes and locks everyone out for the rest of the hour. Read history through GraphQL batches, set a call budget, watch the X-RateLimit headers of real calls (gh api rate_limit lies for the vault's fine-grained token), and never poll gh in a loop."
date: 2026-10-13
---

# Share the GitHub budget

**Rule.** Before a script or loop makes more than a few hundred GitHub REST calls, count them and cut them:
read run and job history through GraphQL batches, give the script a budget it stops at, and watch the
`X-RateLimit-Remaining` header of its own calls. Never poll `gh` in an `until`/`while … sleep` loop.

**Why.** lothsahn, 2026-10-13: "Why was github rate limiting us? What was causing the majority of the github calls?"
(w1185). From 00:04 to 01:04 UTC every worker, the portal's blocker watch and its token check got
`HTTP 403: API rate limit exceeded for user ID 10092359`. The token check reported false "read refused" banners
(w1186), and the cancel commands for paused CI runs failed for half an hour. Three CI-history surveys spent two hours
of budget in about 50 minutes:

- **w1167** (CI placement, beast) ran `minutes.py` five times between 23:24 and 23:57. Each run made one
  `gh api …/actions/runs/<id>/jobs` call per run (1,887 runs) plus one list call per workflow per day, with 8
  threads: about 4,600 REST calls (1,887 measured from its log, the rest estimated).
- **w1173** (ff-factory test fixes, lothdesktop) ran `survey2.sh` with `xargs -P 8` from 23:58 to 00:11: one jobs
  call per attempt plus one `gh run view --job <id> --log` per job, giving 1,963 job logs. The second hour ran out by
  00:12:58.
- **w1175** (CI stats, lothdesktop) read 4,349 runs through GraphQL, which has its own budget, and was then refused
  after about 12 REST log downloads.

Nothing warned them. `gh api rate_limit` answered "remaining 5000, used 0, reset one hour from now" at 23:40, 00:04,
00:12 and 00:31, on two machines, while real calls in the same seconds were refused. For the vault's fine-grained
token it reports a bucket nobody uses. GitHub's request id ends in the call's Unix time in hex
(`…:6ACD756C` = 00:03:56 UTC), which dates a refusal exactly.

**How to apply.**

- **Count first.** Calls = list pages + one per run + one per job log. A `gh run view --job --log` is more than one
  call (the job, its run, the log). Over about 500: redesign before running.
- **Batch history through GraphQL.** `nodes(ids:[<run node_id> …])` → `checkSuite.checkRuns { conclusion startedAt
  completedAt steps }` reads 50 runs per query at cost 1 (w1175). Failed test names come from the check run's
  annotations, not from job logs. Download a log only for the few runs you must read, and cache it in `$TMPDIR` so a
  rerun of the script does not fetch it again.
- **A budget the script enforces.** Run with `gh api -i` (or read the response headers) and stop when
  `X-RateLimit-Remaining` falls below 1,500: the portal and every other worker need the rest. No more than 2 at a time
  (`xargs -P 2`), not 8. Don't trust `gh api rate_limit`.
- **No gh poll loops.** A wait for CI is `blocked_on` with `ci:<owner/repo>#<n>`. w1167's
  `until gh run list …; sleep 15` made 2 calls every 17 s and ran on for 25 minutes after the limit, printing 153
  refusals.
- **When refused:** stop all gh calls until the reset the 403's `X-RateLimit-Reset` header names. Do not retry in a
  loop, and say in your report that the account was rate-limited.
