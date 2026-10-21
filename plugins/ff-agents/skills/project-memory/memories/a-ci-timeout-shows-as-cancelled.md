# A CI job past its time limit ends "cancelled", like a run a newer push replaced

**Learned:** 2026-10-21, w1674 and w1675 (FinalFactory PR #2129).

From #2006 on, every master batch (`master-batch.yml`) hung and hit the job's `timeout-minutes: 150`. GitHub marks such a
job `cancelled`, the same conclusion a superseded run gets, and FF Factory's portal (`server/masterBatch.ts`) reads a
`cancelled` run as "nothing to read". So 141 batches in a row gave no verdict, and nobody noticed for two days.

**How to apply:**
- To tell a timeout from a supersede, read the job's annotations or its times (`gh api
  repos/<o>/<r>/actions/runs/<id>/jobs`): a timeout says "The job has exceeded the maximum execution time of …" and
  lasts exactly the limit.
- A script that drives a long leg (an editor, a player, a bisect) gives each leg its own limit, ends the hung process
  group itself, prints the end of its log, and reports a failure inside a budget under the job's limit. Then the hang
  is a red verdict that can be bisected, never a cancelled job. The model: `master-batch.py` `RUN_LIMIT`,
  `SMOKE_LIMIT`, `--budget-minutes`, plus a step `timeout-minutes` as the backstop.
- A test that hangs only after other tests ran in the same editor passes when run alone. Don't call it flaky: confirm
  and bisect it in the same shape as the run that hung.
- Related: [[embedded-package-tests-join-the-suite]].
