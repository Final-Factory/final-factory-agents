---
name: research-the-decision-not-the-topic
description: "Research questions come from the choices you are about to make, each labelled measured, sourced or guess. The Reddit campaign of October 2026 was researched by topic, and its bid was never a question. A CI or build safeguard (a check, a cache purge, Burst or IL2CPP, a test category) is turned off or removed only after finding why it is there and saying what coverage is lost; prefer a fix that keeps it, and hand a removal up as a person's decision (w4817's ShaderCache cap, w5025's Burst-off gate, both reversed by lothsahn)."
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

## Build the pick the person saw: its still, checked against their words (w1323, w2580, 2026-10-31)

**Rule.** When a person picks a design, mock, model or asset, which one they meant is a decision you are about to make,
and a letter or a label alone is a guess. Name the pick by the still they saw (its path or link) and by what is visible
in it: where on screen, its look, the prefab, model or toggle state. Before you build, read the person's own words about
it against that still. If they fit, write down how; if they point at another option (a position, a panel, a look that
is another still's), ask one question with the stills side by side, instead of building either. The merge or OK stills
show the built result beside the picked still.

**Why.** The second correction of one kind, so it carries a tool check.

- w1323, 2026-10-15, assembler glow lines: the brief and the worker assumed Ben's screenshot showed the classic
  assembler and changed the classic prefabs. Ben: "what no, i was talking about updating the new assembler model, not the
  old one lol". The screenshot itself showed which model it was; nobody named what was in it.
- w2580, 2026-10-31, the Station Info redesign: a card offered four mocks, A to D, with stills. The relayed pick was
  "C, the Tiles", with Ben's words "i like the tiles but i'm worried it might get cut off by the objectives panel". The
  worker built the bottom-centre tiles mock. Ben: "That's not the hover panel mock I chose. I wanted the tile on the left
  above the controls panel", the card mock at the bottom left. The C and D stills had not rendered on his card (w2664,
  fixed in ff-factory PR #781), so the letter he picked was not the picture he had in mind, and his worry about the
  objectives panel already pointed at a left-side mock.

**How to apply.**

- The brief and your first step carry a `Picked (<who>):` line: `still:` the file or link of the option they picked,
  `shows:` what is visible in it in a sentence, `words:` their own words quoted, `matches:` how those words fit that
  still. `python "$FF_SKILLS/evidence-gate/pr_evidence.py" --pick <brief or note> [--brief <read_work text>]` checks it
  before you build (no `beside:` yet), and fails a bare letter or label.
- A screenshot or a still the person sent is a pick too: name the model, prefab or panel in it, and how you told (its
  shape, a toggle such as `new-models`, the asset path you matched it to), before you change anything.
- A conflict is one `waiting_on_person` question with the conflicting stills as previews and each option as an answer,
  not a guess and not a build of both.
- The pull request's Evidence carries the same `Picked:` line with `beside:` a still of the built result beside the picked
  still; `pr_evidence.py` fails a PR whose brief or evidence names a pick ("Ben picked C", "option B", "C, the Tiles")
  without it, or with a letter where the still should be. `Picked: n/a (<why>)` when what was chosen was no design (a
  number, a cut depth).
- An orchestrator relaying a pick relays the option's still path and what it shows with the letter, and the person's own
  words with it; it opens the still itself first and checks the card showed it (w2664: the previews had not rendered).

## Name the part the person's words describe, then edit that part (w2195, w2992, 2026-11-04)

**Rule.** A person's descriptive word ("taller", "spiky", "redder", "bigger") belongs to one object or one part of it,
and often it is not the thing you are about to change. Before a design, concept or model edit, write three lines in your
notes (a `Reading:` block in the first review note or the brief):

1. **Words → part.** For each descriptive word the person used: the object or part it described, in their terms, with
   the still or clip frame where they could see it.
2. **Edit target.** The object or part this edit changes.
3. **Same or not.** If the word described a neighbour, a reference, a different part or a thing that is to be replaced,
   the trait does not carry over. Ask what the person wants for the target, or design it from what the target is for.

Check the reading against the still or clip the person was looking at, not against your memory of the topic. If it is
still ambiguous after that, put the reading in the first review note, so the critic judges against it and a wrong
reading is caught before the person sees it. A fix whose diff is about the wrong part passes any critic that only asks
"does it look like the brief"; so the critic also asks "did the edit touch the part the person named".

### Why (two corrections of the same kind)

- **w2195, Shield Generator, 2026-10-26.** Asked to "move the main structure itself up more a bit", the worker stretched
  the mast and fins. The critic passed it. Ben: "i want the platform itself taller, not just the top spire thing". The
  words named the platform; the edit changed the attachments on top of it.
- **w2992, Dyson hub concepts, 2026-11-04.** Ben remarked that the big spinning collector under the platform was spiky.
  The worker made every new hub concept spiky (Needle, Urchin crown). Ben: "i dont like the spikeyness lol. i was just
  saying the big spinning thing under it was spikey. make it make sense as the hub where power is being routed from the
  dyson swarm". A remark about a neighbouring object was read as a style request for the hub.

### How to apply

- Before the first concept prompt or model edit, write the `Reading:` block. Name parts by what is on the picture
  ("the platform slab", "the spinning collector under it"), not by the file's node names.
- Word about an object next to the target, or about the thing being replaced, is context, not a trait to copy. If the
  person's remark was a complaint, the trait is usually one to avoid in that object, and says nothing about the target.
- Look at the after still beside the before: the changed pixels must be the named part. Anything else that moved is
  listed, and was either asked for or put back.
- Brief the critic with the `Reading:` block (the person's words and the part each refers to, not what you did). It
  fails an edit that left the named part as it was or changed another part instead.

## A CI or build safeguard is removed only after you know why it is there (w4817, w5025, 2026-11-21)

**Rule.** Before a change turns off, skips, caps or removes a safeguard in CI, a build or a test run (a check or a
required job, a cache purge or a clean rebuild, a compile mode such as Burst or IL2CPP, a test category, a timeout, a
retry limit, a validation step), you:

1. **Find why it is there.** `git log -S '<the line>' -- <file>` or `git blame` on the line, the comment beside it, the
   docs it names (`Documentation/CI-Runs.md`, the script's header), and the request or PR that added it (`Request: wNNN`
   in its body). A comment that says "on purpose" or quotes a person ends the question: the safeguard stays.
2. **Say what coverage is lost** if it goes, in one plain line: what bug class would no longer be caught, and where else
   (if anywhere) it still is.
3. **Prefer a fix that keeps it.** Make the slow or flaky thing fast or steady with the safeguard on: wait for Burst's
   background compile instead of turning Burst off, speed the build some other way instead of keeping a cache the
   nightly clears.
4. **If removing it still looks right, hand it up as a decision**: `waiting_on_person` (or `hand_up_requests`) with the
   reason it exists, the coverage lost, the fix you tried that keeps it, and your pick. Do not merge the removal on your
   own judgment, however green CI is: CI cannot tell you what it has stopped checking.

The PR that touches a safeguard says all four in a `## Safeguard` paragraph: why it exists (with its source), what is
lost, the keeping fix you tried, and who decided.

**Why.** Two corrections of the same kind from lothsahn in two days, both a worker making CI faster or steadier by
taking a safeguard out, without asking why it was there:

- w4817 (PR #3988, 2026-11-20) stopped the nightly from purging `Library/ShaderCache` below a 2 GB cap, to cut cold
  shader compiles (over 2,000 s against 23 s warm, measured). lothsahn: "Wait a second, the point of the nightly build
  was to clear and rebuild the shader cache so that if there was any corruption it would get regenerated". w4869
  reverted it (PR #4005). The purge script's header now says so, and the game repo's
  `NightlyShaderCachePurgeGuardTest` (w5030, PR #4113) fails a change that takes ShaderCache out of the purge.
- w5025 (PR #4111, 2026-11-21) set `UNITY_BURST_DISABLE_COMPILATION=1` on pre-1.0's merge gate to stop a cold
  synchronous Burst compile from stalling `HelpButtonTooltipTest` 285 s. lothsahn: "No, we need to run tests with
  burst. It's critical because it can have impacts on system behavior". It is being undone by waiting for Burst's
  background compile instead (w5028's PR #4112, w5029), the keeping fix step 3 asks for.

In both the speed-up was measured and real; what was missing was the question why the cost was being paid. A safeguard
costs time on every run and pays off once in a long while, so a worker looking at one slow run always sees only its
cost.

**How to apply.** Read the diff of your CI, workflow, build-script or test-runner change for anything it turns off or
narrows: an env var or flag set to disable (`UNITY_BURST_DISABLE_COMPILATION`, `--burst-disable-compilation`,
`-testCategory '!...'`, `continue-on-error: true`, `if: false`), a deleted step or job, a folder taken out of a purge or
a clean, a check made conditional. Each one goes through the four steps before the PR leaves draft.

A removal a person decided is the model, not a precedent to copy: master's merge gate runs Burst off because lothsahn
chose it for that gate (w1759: "make them run much faster. Some coverage loss is acceptable"), and its comment in
`.github/workflows/main.yml` names what moved to the Burst-on master batch. That decision covered master's gate only;
w5025 carried it to pre-1.0 without asking and was reversed. A decision for one gate, branch or job is asked again for
the next.
