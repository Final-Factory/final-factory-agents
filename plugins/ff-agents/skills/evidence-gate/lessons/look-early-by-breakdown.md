---
name: look-early-by-breakdown
description: "After anything goes live, the first check comes within hours, reads the breakdowns that would show each likely failure, and compares them with numbers written down beforehand. Totals cannot fail."
date: 2026-10-02
---

# Look early, by breakdown, against a written expectation

**Rule.** Before the action, write the three likeliest ways it fails and what would show each,
and the numbers you expect. Schedule the first check early. Read the breakdowns, not the total.
If reality is far off, stop and diagnose before changing anything.

**Why.** The Reddit campaign of 2026-10-01 was read at about +1 h, +3 h, +5 h and +13 h. Each
time the worker reported totals: "nothing looks wrong", then "well behind the pace". No expected
number had been written, so no check could fail, and each check happened because the orchestrator
asked. The first review had been planned for 48 hours in, by ad and ad group.

At 13 hours the caps were raised without a diagnosis. At 21.6 hours someone read the country
table: the two cheapest countries in the ad group had nearly all the impressions, and the US had
almost none. By then total spend was back on pace, so the total looked healthy while nearly all
of it went to the wrong countries.

The plan had also reasoned that a cap set too low "under-delivers, which costs nothing". In a
seven-day sale, each lost day is a seventh of the window.

**How to apply.**

- In the record: **fails if** (three failures, each with its signal), **expect** (numbers at the
  first check), **first check** (when, which breakdowns), and the result that means stop.
- Pick breakdowns that separate the failures: for ads, country, ad group and creative; for a
  release, version and platform; for a multiplayer fix, host and client.
- Use `wake_me` so the check happens when it is due, not when someone asks. A check that recurs
  (every hour, each morning) is an FF Factory orchestrator's `set_timer`, set once; `wake_me` is
  one-off and a person's message cancels it.
- A check that returns totals only is incomplete. Say so and read the tables.
- Off the numbers: pause what is off, name which failure it is, report. An adjustment is a new
  decision with its own basis.
- For ads the first check is within 2 hours and the tripwire is half the expected pace. Ben
  accepted both as starting values on 2026-10-02; they are settings in ff-marketing's `ffads`.

## A bulk GitHub read counts its calls and watches the shared budget (w1185, 2026-10-13)

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
