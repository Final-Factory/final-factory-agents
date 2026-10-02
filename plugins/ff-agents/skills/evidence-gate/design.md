# Evidence gate: why it exists and how it is built (w208, 2026-10-02)

The rule and the checklists are in [SKILL.md](SKILL.md). This file is the reasoning: what went
wrong, what each mechanism is for, where it lives, and what Ben decided.

**In short:** the Reddit research covered the topic "Reddit ads for games" and never the decisions
the campaign needed, and nothing in the harness asked what a number rested on. Reddit's own
recommended bid was on screen and was set aside for cheaper figures from other studios' campaigns.
The fix is one rule with tools behind it. Before anything that spends, publishes, changes a live
setting, releases, merges a simulation or visual change, or deletes, the agent lists each choice
with its basis (measured, sourced or guess), settles its own guesses by research, names how it
could fail and looks within hours. The agent enforces it on itself. A person confirms money,
what the rules reserve for them, and forks research could not settle.

## What happened (from the records)

Sources: the briefs and logs of requests w134 and w207 in the FF Factory work ledger, ff-marketing
branch `reddit-ads-mp-launch-800` (PR #34) and PRs #36 and #37, game PRs #884, #886 and #913, and
four entries in Ben's orchestrator memory.

1. **The brief asked for topics, and the research answered topics.** The brief asked for research
   on "bidding (CPC/CPM, typical costs for gaming)". The research note scoped itself to "only the
   gaps left by" earlier notes. It read Reddit's setup page for the budget advice and did not take
   the bid advice from the same page: "ideally one close to the higher suggested bid amount".
   Nobody had written down "what cap wins US auctions this week?" as a question.
2. **Reddit's own number was seen and overruled by a source about something else.** The as-built
   record notes Reddit's recommended bid range for each ad group and calls it "far above what
   indie games report paying". The caps went in at about a third of the range's low end. The indie
   figures came from blended countries, long runs and small daily budgets. The cap had a link, so
   a plain "sourced or guess" label would have passed it.
3. **The failure was priced at zero.** "A cap that is too low under-delivers, which costs
   nothing." In a 7-day sale each day is a seventh of the window, and with six countries under one
   cap delivery did not stop: it moved to the cheapest countries.
4. **No expected numbers, so every check said "nothing wrong".** Checks at about +1 h, +3 h, +5 h
   and +13 h reported totals. The first review was planned for 48 hours in. The country table was
   first read at 21.6 hours: the US had almost no delivery, and the two cheapest countries in the
   ad group had nearly all of it. (The numbers are in the private marketing repo.)
5. **The gate checked permission, and it was not on the path.** `ffads` validated caps, dates, UTM
   tags and file hashes. It had no platform adapter, so the campaign was switched on by hand, and
   Ben's informal go was written into a notes field when `ffads approve` refused it.
6. **Guesses became recommendations on the way to Ben.** The orchestrator's brief told it to relay
   a worker update "in a line or two" and never asked for a basis. Its own memory entry says it
   relayed the caps, and then a higher range, "as recommendations without asking for their basis".

The game repo had the same shape that week: a claim rested on evidence for a different claim.
#913 merged 37 minutes after it opened with "The `watch_video` review is pending". #886's proof
says "No real station was deconstructed". #884 was verified by position numbers, and Ben then
found the rider drawn with engine exhaust.

Asking Ben more often would not have fixed any of these. He was approving things throughout, with
no way to judge a cap or a clip he had not been shown the basis of.

## The mechanisms

| # | Mechanism | What it does | Where it lives |
|---|---|---|---|
| 1 | Decision record | Before the action, one row per choice or claim: value and basis. MEASURED (how). SOURCED (the source, and why it fits this case; the tool's own docs and on-screen recommendation outrank third parties). GUESS. Research questions come from the GUESS rows. | This skill; the `decision` block of an `ffads` proposal; a pull request's `## Evidence` section |
| 2 | Gate, self-enforced | A GUESS on a row that affects the outcome blocks the action. The agent settles it by research or measurement, about 20 minutes a row, then proceeds on its own. | `ffads lint` (run by `show`, `check`, `apply`, `launched` and CI); `pr_evidence.py`; `make_drafts.py send` |
| 3 | Pre-mortem, expectation, tripwire | Three ways it fails and how each would show. Expected numbers. A first check within hours, by the breakdowns that separate the failures. A stop-and-diagnose rule. | In the record; `ffads launched` and `ffads firstcheck` |
| 4 | Labels all the way up | Reports label each number and recommendation measured, sourced or guess. The orchestrator keeps the labels, sends a guess back to be researched, and never upgrades it. Briefs list the decisions the work must settle. | ff-factory `server/agents.ts`: worker briefs, both orchestrator briefs, the `[worker update]` relay text |
| 5 | Checklists and lessons | Short lists for visual changes, merges, releases, ads and outreach. A miss adds a dated lesson and the checklist line or tool check that would have caught it, in the same change. | `checklists/` and `lessons/` here; `lessons/` in ff-marketing |

### Who is asked what (Ben, 2026-10-02)

"I want the agent to be mostly autonomous. i dont want you to run every decision by me. i just
want YOU to make sure you are making decisions with appropriate context and research. If its
spending actual money then yea, ask me to confirm the value."

So a person is asked only for:

1. **Money**: the value (budget, bid, purchase), once per decision, with the evidence shown. In
   `ffads` that is the approval phrase, printed beside what each choice rests on.
2. **What the rules already reserve for them**: deletes, app settings and deploys, publishing in
   their name, merges that are not pre-approved, releases.
3. **A real fork research could not settle**: the options, with a recommendation.

"Decided by the person" is therefore not a basis an agent can reach for. In `ffads` it is accepted
on a money value, and elsewhere only with a statement of why research could not settle it.

### How skipping is prevented

- `ffads show` prints the approval phrase only when lint passes, and the record is inside the hash
  Ben approves, so filling it in afterwards voids the approval. `launched` and `firstcheck` refuse
  a proposal that did not pass.
- `pr_evidence.py --comment` posts its verdict on the pull request, timestamped before the merge,
  and `--audit` lists merges that had no PASS.
- The orchestrator's brief tells it to send unlabelled numbers back to the worker.
- What no tool can do: see a platform's UI, or judge whether someone looked carefully. Those stay
  rules, backed by the lessons.

### Keeping it proportionate

It applies only when the action is consequential and something that affects the outcome is not
already measured. The record is a few lines. Research is time-boxed. A repeat of a measured setup
cites it and goes. It is never a questionnaire for the person.

Estimated cost (not measured): 5 to 10 minutes for the record, up to 20 minutes per guessed row
(usually one to three), 10 minutes for the first check. For the campaign, about an hour before
launch.

### Settings

The first check within 2 hours and the tripwire at half the expected pace are starting values
Ben accepted on 2026-10-02. In ff-marketing they are `first_check_max_hours` and
`tripwire_pace_fraction` under `"gate"` in `ads/limits.json`.

## Where memory lives, and what a fork gets

| Kind | Home | In a fork |
|---|---|---|
| How to decide, verify and report: rules, checklists, lessons | this skill | yes |
| One system's traps (Unity, ECS, tools) | the `project-memory` skill | yes |
| Marketing checklists and lessons | ff-marketing `lessons/` | with that repo (private) |
| Rules the prompts state themselves | ff-factory `server/agents.ts` | yes |
| One person's preferences | their orchestrator's memory folder; to be versioned in a private repo | no |

A new lesson travels like this: an orchestrator keeps a one-line pointer in its memory and files
a request; a worker opens the pull request in the harness repo; the person approves it. The first
use was Ben's four memory entries, which became the lessons on research, visual verification,
paste text and this flow.

Ben's decision on preference files: general rules always go into the harness repos. One person's
preference files stay out of the public repos and are versioned in a private one, by pointing
`orchestrator.memoryRoot` at a clone that the app commits to. That app change is its own pull
request in ff-factory.

## Prior art

- Pre-mortem: Klein, "Performing a Project Premortem", Harvard Business Review, 2007
  (https://hbr.org/2007/09/performing-a-project-premortem).
- Decision records: Nygard, "Documenting Architecture Decisions", 2011 (https://adr.github.io/).
- Checklists: Haynes et al., NEJM 2009: surgical complications fell from 11.0% to 7.0% with a
  19-item list (https://www.ncbi.nlm.nih.gov/books/NBK143241/).
- Tripwires: Duke's kill criteria, "a state and a date", set in advance
  (https://behavioralscientist.org/annie-duke-quit-mental-models-to-help-you-cut-your-losses/).
- Proportion: Bezos on reversible and irreversible decisions, 2015 shareholder letter
  (https://s2.q4cdn.com/299287126/files/doc_financials/annual/2015-Letter-to-Shareholders.PDF).
- Early checks: canary releases, Google SRE workbook (https://sre.google/workbook/canarying-releases/).
- Other harnesses gate on permission: a Claude Code PreToolUse hook can deny a tool call
  (https://code.claude.com/docs/en/hooks), and a LangGraph interrupt pauses for approval
  (https://docs.langchain.com/oss/python/langgraph/interrupts). This design adds grounds, and
  leaves permission where it was.

## Dry runs

- The Reddit campaign against `ffads lint`: ff-marketing `docs/evidence-gate-replay-2026-10-02.md`.
- The three visual pull requests against `pr_evidence.py`: [replay-2026-10-02.md](replay-2026-10-02.md).
