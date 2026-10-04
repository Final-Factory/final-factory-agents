---
name: evidence-gate
description: "Before any consequential action (spending money, publishing or sending anything, changing a live setting, releasing, merging a simulation or player-visible change, deleting, or reporting a fix as done) and before recommending one, list the choices, say what each rests on (measured, sourced or guess), settle your own guesses by research, name how it could fail and when you will look, then proceed. A person is asked only for money, for what the rules reserve for them, or at a real fork. Holds the working-rule lessons, the visual, merge, release and FFBox desync PR checklists, and pr_evidence.py, which checks a PR's Evidence section. Use before acting on something you have not verified, when writing a brief or a report with numbers or recommendations, and after any miss (add a lesson)."
---

# Evidence gate: research the decision before acting

One rule: **every choice or claim behind a consequential action carries a basis that fits it, and
you do not act while one that affects the outcome is a guess.**

You enforce this on yourself, and then you proceed. It is not a form for the person to fill in.

## When it applies

Both must hold.

- **Consequential.** It spends money, publishes or sends something outside, changes a live
  setting, releases a build, merges a simulation, save, netcode or player-visible change, or
  deletes something you cannot restore. Reporting a fix as done counts too: someone will act on it.
- **Uncertain.** At least one choice that affects the outcome is not already measured for this
  same setup.

A repeat of a setup that has measured results cites them in one line and goes. Reading, drafting,
local edits, tests and ordinary pull requests need none of this.

## The record: a few lines, written before the action

| Choice or claim | Value | Basis |
|---|---|---|
| each thing you are about to set or assert | | MEASURED: how. SOURCED: the source, and why it fits this case. GUESS. |

1. **List the choices first.** Take them from the action itself: every field of the form you will
   fill in, every claim your pull request or report makes ("fixed", "looks right", "no simulation
   change"). Research questions come from the GUESS rows. A topic is not a research question.
2. **MEASURED** means you measured the thing the row claims. A position number does not measure
   how something looks. An editor rig does not measure the built game.
3. **SOURCED** needs a source that fits: same platform, country, version and period. The
   platform's own docs and the value its own screen recommends come first; a third party does not
   overrule them. A source about other conditions is a guess with a link.
4. Then three lines. **Fails if:** the three likeliest ways, and what would show each. **Expect:**
   numbers. **First check:** when, by which breakdowns, and the result that means stop.

Write it where the action is recorded: the proposal, the pull request (`## Evidence`), the release
notes. Otherwise put it in your report.

## The gate is yours to pass

A GUESS on a row that affects the outcome blocks the action. Settle it yourself, in this order:
the tool's or platform's own docs, the value its own screen shows, our own data, other people's
write-ups, a small reversible test. About 20 minutes a row. Record the basis and carry on. Don't
hand the person the question.

Ask the person only for:

1. **Money.** They confirm the value (a budget, a bid, a purchase) once per decision, with the
   record in front of them.
2. **What the rules already reserve for them:** deleting, app settings and deploys, publishing in
   their name, releases.
3. **A real fork research could not settle:** the options, what each rests on, and the one you
   recommend.

**Merging is not on that list.** Once the verification is done and CI is green, merge your own
pull request. Don't stop at an open PR waiting for the person. Hold one only for exceptional risk
or a concrete timing reason, and say in your report which it is and when it will merge.

## After the action

Do the first check when you said you would (`wake_me` brings you back; an FF Factory orchestrator
watching something every N hours or each morning sets `set_timer` once instead, which survives
restarts and its person's messages: FF Factory docs/orchestrators.md, "Timers"), by the breakdowns you
named, against the numbers you wrote. If reality is far off, stop, find which failure it is, and
report. Change nothing on a guess.

## Reports and briefs

- Label each number and recommendation **measured**, **sourced** or **guess**. Say what you saw,
  not what a title, a measurement table or a tool verdict implies.
- A brief for consequential work lists the decisions the work must settle, and says the worker
  settles its own guesses.
- When you pass on someone's report, keep its labels. A guess never becomes a recommendation on
  the way up.
- **Say what every id is, every time** ([lesson](lessons/say-what-an-id-is.md)). Before you send
  anything a person reads, scan it for request ids (w293), PR numbers (#972), commits, worker or
  session ids and sandbox names: each one gets its plain-English words beside it, on every
  appearance, not only the first.

## Checklists: read the one for what you are doing

- [Visual changes](checklists/visual.md)
- [Merges](checklists/merge.md), with `pr_evidence.py` for the pull request's `## Evidence` section
- [Releases](checklists/release.md)
- [FFBox desync PRs](checklists/ffbox-desync-pr.md) (Lothsahn's standing policy, 2026-10-04): classify
  1 report generation only, 2 a game desync fix, 3 capture during play; tests, a 2-peer red/green
  check for 2, a before/after tick and frame measurement for 3 (under 1% merges, above escalates
  through the intake with `PERF-ESCALATION`).
- Ads and outreach live in the ff-marketing repo: `lessons/ads.md` and `lessons/outreach.md`,
  enforced by `scripts/ads/ffads lint`.

## Lessons: the rules this team paid for

One file each under `lessons/`: the rule, why (the incident, dated), how to apply.

- [Research the decision, not the topic](lessons/research-the-decision-not-the-topic.md): the
  Reddit caps came from a topic survey; nobody asked what bid wins US auctions. Label every basis.
- [Settle your own guesses](lessons/settle-your-own-guesses.md): Ben wants agents mostly
  autonomous; he confirms money, reserved actions and real forks, and is not a way out of research.
- [Look early, by breakdown, against a written expectation](lessons/look-early-by-breakdown.md):
  four checks of totals said "nothing wrong"; the country table at 21.6 hours showed the failure.
- [A visual fix is verified by looking](lessons/visual-fixes-are-verified-by-looking.md): a built
  player, a clip that contains the event, the intended look in the person's words; `watch_video`
  is a second opinion.
- [No merge before the review](lessons/no-merge-before-the-review.md): "pending" is not done.
- [Merge your own pull request](lessons/merge-your-own-pr.md): verified and green means merge;
  hold only for exceptional risk or a timing reason, and say which and when.
- [A release lands where SETLIVE says](lessons/a-release-lands-where-setlive-says.md): develop on
  `development`, master on `pre-release`; run `release-status.py`, never recall it.
- [A release is done when its notes are posted](lessons/a-release-is-done-when-its-notes-are-posted.md):
  live on its branch AND the patch notes posted as Max in #dev-patch-notes; no ffdiscord config
  here means the post stays an open step in the report.
- [Keep rm out of long commands](lessons/keep-rm-out-of-long-commands.md): a deletion chained
  into a long command waits on a permission prompt nobody sees.
- [Text for the person to paste is plain](lessons/paste-text-is-plain.md): no code block, no
  formatting, their voice.
- [Say what an id is, every time](lessons/say-what-an-id-is.md): w293, #972, a sha or a sandbox
  name means nothing to a person; put what it is beside it, every time.
- [Lessons belong in the harness repo](lessons/lessons-belong-in-the-harness-repo.md): not in a
  machine's or an orchestrator's memory folder.
- [Verify simulation at a slow host's frame rate](lessons/verify-simulation-at-a-slow-hosts-frame-rate.md):
  per-frame code writes no simulation state; prove a move with a frame-without-heartbeat test and a
  multiplayer run whose host is held near 20 fps (w342/w356: a Steam Deck host forked alone).

## Adding a lesson

After a miss that reached a person, or a near miss a check caught, add the lesson **and** the
checklist line or tool check that would have caught it, in the same change, through
`publish-skills`. A lesson that only says "be careful" is not finished. Keep this list short:
past about twenty, merge or retire entries. Lessons about one system (Unity, ECS, a tool trap)
go to `project-memory`; lessons about how to decide, verify and report go here; marketing ones go
to ff-marketing's `lessons/`.

The reasoning behind this skill, the incident it came from and the prior art: [design.md](design.md).
The week's cases replayed against it: [replay-2026-10-02.md](replay-2026-10-02.md).
