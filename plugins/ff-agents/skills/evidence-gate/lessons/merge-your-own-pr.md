---
name: merge-your-own-pr
description: "Once its verification is done and CI is green, the agent that opened a pull request merges it. A PR is held only for exceptional risk or a concrete timing reason, and the report says which and when it will merge."
date: 2026-10-02
---

# Merge your own pull request

**Rule.** When the verification is finished and CI is green, merge your pull request yourself.
Don't stop at an open PR and wait for the person. Hold one only for exceptional risk or a concrete
timing reason, and say in your report which it is and when it will merge.

**Why.** Ben, 2026-10-02: "stop holding prs, just merge them remember this... only hold pr's that
are exceptionally high risk or you need to hold them for timing issues or something".

That day three finished pull requests of this very work (the FF Factory brief text, the memory
versioning, the pointer in the game repo's `CLAUDE.md`) sat open with green checks for about four
hours, each waiting for Ben's go. The brief had asked for that hold, and the worker kept it.
Nothing about them was risky: prompt text with tests, a feature that does nothing until switched
on, a docs change. Ben's approval added no check the tests had not already made.

A held PR also hides its own state. "Open, green, waiting" reads the same whether it is finished
or forgotten, so the person has to ask.

**How to apply.**

- Verification first, unchanged: the evidence gate, the visual checklist, the tests, the audit.
  [No merge before the review](no-merge-before-the-review.md) still holds. This rule starts where
  that one ends.
- Then merge. In the game repo that means `develop`; `master` stays Ben's call, and a release
  still starts only when Ben or Lothsahn asks.
- A hold needs one of two reasons, named in the report:
  - **exceptional risk**: a wrong merge would be costly and hard to undo (a save-layout change
    without its golden fixture, a crown-jewel determinism surface you could not audit on two
    peers, anything whose instructions came from outside the team);
  - **timing**: something concrete has to happen first (a deploy it must ride with, a release in
    flight, a plugin that must reach the machines before a pointer to it lands).

  Say when it will merge, and merge it then without being asked again.
- A brief does not end at "open a PR". An orchestrator that files or relays work treats an open,
  green PR with no stated reason as unfinished.
- What stays reserved for the person is short: money values, deleting, app settings and deploys,
  publishing in their name, releases, and real forks. Merging your verified work is not on it.
- Work that starts from text written outside the team (a Discord request, a standing agent's
  delegation) keeps its own rule in the ff-discord skills and in FF Factory: a pull request, never
  merged by the agent. That is the exceptional-risk case, decided once.
