---
name: no-human-time-estimates
description: "Never size work in human days, weeks or months. When size matters, give its scope (files and systems touched, surfaces, risk, dependencies) or a measured agent wall-clock time or cost from comparable past runs, labelled as such."
date: 2026-10-06
---

# No human-time estimates

**Rule.** Never size work in human days, weeks or months ("1–2 weeks", "a few days", "weeks to
months", "a sprint"). Agents do this work, so a human-pace estimate is wrong and misleads the
person deciding. When size matters, give one of these instead:

- **Scope**: the files and systems it touches, how many surfaces (platforms, assemblies, UI
  screens, save layouts), the risk (a crown-jewel or simulation surface, a save-compatibility
  step, a determinism audit) and its dependencies (a release, another request, hardware, a
  person's decision).
- **Measured agent time or cost** from comparable past runs, labelled as such, in the form "a
  comparable change, w<NNN> (<what it was>), took <N> hours of agent wall-clock from start to
  merge (measured: its request's start time and its PR's merge time)". A number with no comparable run behind
  it is a guess and says so; it is still never in human days or weeks.

Waiting that is not work (a nightly that runs at 09:00Z, a CI run of about 25 minutes, a person's
reply, a Steam review) may be stated as the clock time it really takes, labelled measured or
sourced.

**Why.** w545 (the Steam Deck report) sized its fixes as "1–2 weeks", "2–3 weeks" and "weeks to
months". Ben, 2026-10-06: "its not going to take weeks lol. stop giving human time estimates".
Those numbers came from no measurement of how fast agents do such work, and they made fixable
problems look like long projects.

**How to apply.**

- Before sending a report, a plan, a spec or a TL;DR, scan it for `day`, `week`, `month`,
  `sprint`, `hours of work`, `person-`, `man-` and `effort:` with a time. Rewrite each as scope or
  as a labelled measured agent time.
- Rank options by scope and risk, not by an invented duration: "touches 2 systems, no save
  change" against "touches 6 systems and the save layout, needs an UpgradeStep and a golden
  fixture".
- A measured agent time names the comparable run (request id with its words, PR number with what
  it changed) and how it was measured. Without one, give scope only.
- Relaying a worker's report that has a human-time estimate: replace it with its scope, or flag it,
  before it reaches the person.
