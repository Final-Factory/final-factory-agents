---
name: a-fix-names-its-player-report
description: "When a worker confirms which player crash or desync report its fix addresses, it records the link: a `Report: <report id>` line in the PR description, or the report id as a subject of its request (request_work / update_work `subjects`). A brief that only mentions a report claims nothing, and FFBox keeps showing the report open."
date: 2026-10-05
---

# A fix names the player report it fixes

**Rule.** When you confirm that your fix addresses a player's crash or desync report (an id like
`20261005T035612Z-crash-6102d405dc`), record the link where the ledger reads it:

- in the PR description, one line per report, on a line of its own: `Report: <report id>`
  (a worker can always do this);
- or as a subject of the request: `request_work {subjects: [<report id>]}`, or later
  `update_work {id, subjects: [<report id>]}` (an orchestrator, for its person's request).

Only a report you confirmed the fix addresses, never one you only read for context.

**Why.** FFBox shows each report's state on its /intake page, in `ffbox_activity reports` and in
`signatures`, and a report stays NEEDS-INFO, unfixed, until FF Factory tells it the fix shipped
(`report_fixed`, w502). FF Factory tells it only for reports a finished request claims: its
`report:<id>` keys, which come from its subjects, its title, an intake diagnosis that joined it, or a
merged PR's `Report:` lines. A brief's ids are references and claim nothing (w343). On 2026-10-05 the
Build 76 crash reports 20261005T035612Z-crash-6102d405dc and 20261005T035747Z-crash-1216e47e7d were
fixed by w414's PR #1064, shipped in Builds 77 and 78, and still read NEEDS-INFO: w414's brief named
them only as references. Lothsahn: "make it automatic going forward".

**How to apply.**

- Write the line when you confirm it, before the PR merges; FF Factory reads merged PRs' `Report:`
  lines every five minutes and marks the reports fixed once the fix is in a release.
- Several reports, several lines, at most twenty. An id quoted mid-sentence is not read.
- Pushing straight to develop with no PR: ask your orchestrator to add the subjects instead.
- Nothing is posted to Discord about a report; FFBox only records it.

Related: [a fix PR names its Discord report](a-fix-pr-names-its-discord-report.md). The checklist
line: [merges](../checklists/merge.md).
