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
- Use `wake_me` so the check happens when it is due, not when someone asks.
- A check that returns totals only is incomplete. Say so and read the tables.
- Off the numbers: pause what is off, name which failure it is, report. An adjustment is a new
  decision with its own basis.
- For ads the first check is within 2 hours and the tripwire is half the expected pace. Ben
  accepted both as starting values on 2026-10-02; they are settings in ff-marketing's `ffads`.
