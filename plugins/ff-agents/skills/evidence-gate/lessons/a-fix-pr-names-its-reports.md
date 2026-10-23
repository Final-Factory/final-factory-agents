---
name: a-fix-pr-names-its-reports
description: "A PR that fixes a Discord report carries the report's own link before it merges, `Discord: https://discord.com/channels/<guild>/<thread>` for a thread or `.../<guild>/<channel>/<message>` for a message in a channel; FFBox tells the reporter from that line and from nothing else. A request closed as already fixed by another PR names it: `RESOLVED: already fixed by PR #N`. When a worker confirms which player crash or desync report its fix addresses, it records the link: a `Report: <report id>` line in the PR description, or the report id as a subject of its request (request_work / update_work `subjects`). A brief that only mentions a report claims nothing, and FFBox keeps showing the report open."
date: 2026-10-05
---

# A fix PR names the reports it fixes

Two kinds of report, two lines, both read by machines from whole lines of the PR description. (Until w1288 these were
two lessons, `a-fix-pr-names-its-discord-report` and `a-fix-names-its-player-report`; merged to keep the lesson count
at its cap.)

## Its Discord report

**Rule.** Before a pull request that fixes a bug someone reported on Discord merges, its description
has one line per report, on a line of its own:

- a thread (#bug-reports, a forum): `Discord: https://discord.com/channels/<guild id>/<thread id>`
- a message in a channel (#ask-assistant, a chat): the original message's own link,
  `Discord: https://discord.com/channels/<guild id>/<channel id>/<message id>`

When you close an intake request because another, already merged PR fixed it, name that PR in the
marker: `RESOLVED: already fixed by PR #1076`.

**Why.** FFBox posts the "Fixed in PR #N, coming in version X and later." notice to the reporter,
and it finds who to tell in two ways only: the `Discord:` lines of the merged PR (ffbox
`scripts/ffwatch.py` `PR_DISCORD_LINE_RE`, `pr_discord_links`, anchored to a whole line) and FF
Factory's ledger answer for a thread Max escalated. On 2026-10-05 w436 (FFBox conversation 692, a
player in #ask-assistant whose range rings darkened the screen) was closed as already fixed by #1076,
which shipped in Build 78, and the player was never told: #1076 came from another request and had no
`Discord:` line for that message, and the ledger answer carried no PR (fixed in FF Factory by w480).
Lothsahn: put the original message link in the PR so FFBox can report it.

**How to apply.**

- Copy the link from the report itself (the request's source URL, the escalation brief's `Discord:`
  line), not a link to a reply or a later message.
- Several reports, several lines, at most ten. A link quoted mid-sentence is not read.
- A change that did not come through a pull request (master takes none directly): put the line in the commit body.
- Never post the "fixed" notice yourself: FFBox does, once, from these lines.
- `RESOLVED: already fixed by PR #N` with exactly one PR number in the line: FF Factory looks up that
  PR's merge and release and the escalated thread hears "Fixed in PR #N, coming in version X".

## Its player report

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
- A change that did not come through a pull request (master takes none directly): ask your orchestrator to add the subjects instead.
- Nothing is posted to Discord about a report; FFBox only records it.

The checklist lines: [merges](../checklists/merge.md).

## Every bug thread has an owner (w1783, 2026-10-22)

**Rule.** A bug sweep covers every thread in its window, not titles someone picked: list every #bug-reports and
dev_bug_reports thread created or active in the window, open or archived, and give each one a row (the request or PR
that owns it, a decision that it is not a bug, or the fix you start). And an owner's acknowledgement in a bug thread is a
filed request: when Ben or Lothsahn answers a report as a real bug, in any words ("Will fix", "yeah that's a bug",
"good catch", "oops", "on it", "I broke this"), that thread has a request of theirs, approved by that reply, with the
thread as its subject. A request owns a thread by its subjects or source; a sweep's window or a brief that only
mentions the thread does not.

**Why.** Ben corrected the same miss twice on 2026-10-22. First: "I asked you to go through the bug reports and look at
them and make sure you file a report for each of them or spawn a worker or whatever. Clearly you didn't do that" (the
w1773 sweep was scoped from thread titles an orchestrator picked, so newer and older threads, the multiplayer invisible
asteroid among them, had no request). Then: "when I respond to a Discord thread and say, we'll fix, that means you're
fixing it" (the w1779 audit found two threads with his "Will fix" and no request), and "it doesn't have to literally
say, will fix. Like, any indication that I'm acknowledging it as a bug is sufficient. Like, you're supposed to be
intelligent."

**How to apply.**

- FF Factory now does both by itself (ff-factory `server/bugThreads.ts`, docs/intake.md "Every bug thread has an
  owner"): a model judges every owner reply and files the owner's approved request, and an hourly coverage check files
  each thread of the last seven days that no request, no PR `Discord:` line and no FFBox PR owns, for a reviewer. Its
  journal lines (`portal_logs` grep "bug threads") list today's unowned threads: read them instead of sweeping by hand.
- A sweep you are asked for still starts from the full thread list of its window, never from a list of titles, and
  its report has one row per thread.
- A judgement of "is this an acknowledgement" is a model's reading of the whole message, never a phrase list; a
  question back to the reporter, "works as designed", "a feature request" and "already fixed in <build>" are not.
- When you take a thread's work, make the thread a subject of your request (`request_work` / `update_work` `subjects`),
  so the check and FFBox's ledger check see it as owned.
