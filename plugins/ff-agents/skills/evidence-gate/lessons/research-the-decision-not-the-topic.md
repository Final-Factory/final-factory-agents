---
name: research-the-decision-not-the-topic
description: "Research questions come from the choices you are about to make, each labelled measured, sourced or guess. The Reddit campaign of October 2026 was researched by topic, and its bid was never a question."
date: 2026-10-02
---

# Research the decision, not the topic

**Rule.** Before a consequential action, list the choices you are about to make and what each
rests on: measured, sourced (and the source fits this case), or guess. Research the guesses. The
tool's own docs and the value its own screen recommends come before anyone else's numbers.

**Why.** The launch-week Reddit campaign for the Multiplayer Update (2026-10-01). Ben asked for
research on Reddit ads for games, and it was done: several notes, dozens of sources. The brief
listed topics, among them "bidding (CPC/CPM, typical costs for gaming)". The research answered
that. Nobody had written down the question the campaign needed: what bid wins US auctions for
this audience this week.

- The research note read Reddit's setup page for its budget advice and passed over the bid advice
  on the same page: "ideally one close to the higher suggested bid amount".
- Ads Manager showed a recommended bid range for each ad group. The worker recorded it and set a
  cap at about a third of its low end, because the range was "far above what indie games report
  paying". Those figures came from other studios' campaigns: blended countries, long runs, small
  daily budgets. For the US alone the platform's range was higher still.
- The cap had a link. A label of "sourced" alone would have passed it. The source did not fit the
  case.

For the first day the main market got almost no delivery, and the spend went to the cheapest
countries in the ad group. Ben: "you completely missed researching the basic question of what is
the best auction price for a Reddit ad for the U.S."

**How to apply.**

- Take the list of choices from the action itself: every field of the form, every claim of the
  pull request. A brief that lists topics gets topic research, so a brief for consequential work
  lists the decisions.
- For each SOURCED row, write why the source applies here: same platform, country, version,
  period. If you cannot, it is a guess with a link.
- When the tool you are about to use shows a recommendation, record it. Overruling it takes your
  own measurement, or the person's decision with the recommendation in front of them.
- In ff-marketing, `scripts/ads/ffads lint` enforces this for ad proposals. The campaign's
  numbers and its replay against the lint are in that repo
  (`docs/evidence-gate-replay-2026-10-02.md`); ad report numbers stay out of public repos.
