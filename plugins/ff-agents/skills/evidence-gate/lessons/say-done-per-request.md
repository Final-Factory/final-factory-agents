---
name: say-done-per-request
description: "A worker ends its report with `DONE: wNNN` when every step of that FF Factory request is finished, the steps after the merge included, and answers a wrap-up or an \"Is it done?\" with DONE or one line of what is left. Never DONE while something is left."
date: 2026-10-05
---

# Say DONE per request, and only when every step is done

**Rule.** In FF Factory, when every step of a request you were given is finished, the steps after
the merge included (a paired audit, a first-hour check of a release, the patch notes posted),
end your report with a line `DONE: wNNN`, one line per request, several allowed. The ledger
closes the request on it, with your report as the note. Never write it while something is left:
say in one line what is left instead. When a message starts with `[wrap-up]` (you are being
moved to another request) or `[ledger cleanup] Is wNNN done?`, answer each request it names with
`DONE: wNNN` or `wNNN: still open: <what>`, then carry on with your current work.

**Why.** 2026-10-05 (w419, Lothsahn): w342 (moving deletion onto the fixed tick) was finished. Its
PR #1024 merged at 01:43 UTC, the paired audit ran before the merge, and Build 76's first hour
showed no desyncs. But the ledger read "its brief asks for a step after the merge" and kept it
open, and its worker went on to w414 in the same session. Nothing in a worker's report said
"this request is done", so w342 neither stalled nor closed, and it showed as active.

**And every check the brief's "Done" names.** 2026-10-08 (w704, logistics bots): the brief's Done
said "SP and MP verified by a run (say what was run)". PR #1263 merged with "Not verified: a live
built-player SP/MP game", the worker wrote DONE, and Ben reopened the request when the live
single-player scenario then read 0 of 100 delivered. Asked again, the worker answered that the
failing run "is from the first run, before I found the cause"; `git merge-base --is-ancestor`
shows the build it ran (8bba83e65) already held both fix commits, and the real cause was the
scenario's fixture (no power, and supply bots that carry 0 before the research; PR #1270).

**How to apply.**

- The ledger refuses a DONE, and tells you what is missing, while a PR of the request is still
  open, for a release whose report does not say it is live and link the posted notes, and when the
  brief asks for a step after the merge that your report does not say how it went. Put that
  evidence in the same report as the DONE line.
- The line is only `DONE: wNNN` (markdown around it is fine). Inside a sentence it does not count.
- Only a worker linked to the request counts. Done with something you were not given? Say so in
  your report, and the dispatcher closes it.
- The ledger acts on the line once FF Factory runs w419 (merged 2026-10-05, live at its next
  deploy). Until then the line is still the clearest way to say a request is finished.
- FF Factory's own docs: `docs/orchestrators.md`, "Ledger cleanup" (the DONE marker, the wrap-up,
  the "Is it done?" follow-up).
- Read the brief's Done line item by item before the DONE line. A check it names that you did not
  run is "still open", even when the PR's "Not verified" says so honestly.
- A failed check is explained by evidence, never dismissed: "that run predated the fix" needs
  `git merge-base --is-ancestor <fix> <build commit>` to say so, and "the fixture is wrong" needs
  the fixture fixed and the check rerun green.
