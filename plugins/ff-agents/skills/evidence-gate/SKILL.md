---
name: evidence-gate
description: "Before any consequential action (spending money, publishing or sending anything, changing a live setting, releasing, merging a simulation or player-visible change, deleting, or reporting a fix as done) and before recommending one, list the choices, say what each rests on (measured, sourced or guess), settle your own guesses by research, name how it could fail and when you will look, then proceed. A person is asked only for money, for what the rules reserve for them, or at a real fork. Holds the working-rule lessons, the done, delete, visual, UI, Steam Deck, merge, release and FFBox desync PR checklists, and pr_evidence.py, which checks a PR's Evidence section (for a UI change its content, style, per-still and real-rate clip lines) and, for a changed shader or material, its Used by section. Use before acting on something you have not verified, when writing a brief or a report with numbers or recommendations, and after any miss (add a lesson)."
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

## Move only what the person asked to move

**A hard rule for every UI change** (Ben, w894, after four corrections: "stop moving panels around that I don't ask you
to move around. It's driving me crazy."; [lesson](lessons/a-ui-change-leaves-the-rest-of-the-screen-as-it-was.md#move-only-what-the-person-asked-to-move-the-hard-rule-w894-2026-10-10)).
Never move, re-anchor, restack or regroup an existing panel, HUD element or hover panel unless the brief quotes the
person asking for that exact element to move. Census 1920x1080, 1280x800 and 1280x800 docked; `ui_layout.py moves` and
`pins`; `pr_evidence.py --brief` fails any move not asked for in the brief's own words and any broken pin
([UI checklist](checklists/ui.md), item 22).

## Reports and briefs

- Label each number and recommendation **measured**, **sourced** or **guess**. Say what you saw,
  not what a title, a measurement table or a tool verdict implies.
- A brief for consequential work lists the decisions the work must settle, and says the worker
  settles its own guesses.
- When you pass on someone's report, keep its labels. A guess never becomes a recommendation on
  the way up.
- **A claim about what another system does comes from that system** ([lesson](lessons/check-the-other-systems-live-config.md)).
  Before you relay "X is not built", "nothing will investigate this" or "that is off" from one
  system's tool about another, read the other system's live config or state (for FFBox,
  `ffbox_activity show config` / `show signatures`) and quote the key and value, or say unknown.
  For what FF Factory itself did (a deploy, a clean-up, an update, a restart), read the portal's own logs with
  `mcp__machine__portal_logs` (w920) and name the source and window; never infer it from the code.
- **Say what every id is, every time** ([lesson](lessons/say-what-an-id-is.md)). Before you send
  anything a person reads, scan it for request ids (w293), PR numbers (#972), commits, worker or
  session ids and sandbox names: each one gets its plain-English words beside it, on every
  appearance, not only the first.
- **No human-time estimates** ([lesson](lessons/no-human-time-estimates.md)). Before you send a
  report, plan or TL;DR, scan it for sizes in days, weeks, months or sprints ("1–2 weeks",
  "weeks to months"). Rewrite each as scope (files and systems touched, surfaces, risk,
  dependencies) or as a measured agent wall-clock time or cost from a named comparable run,
  labelled measured. No comparable run: scope only.
- **On ff-factory, `npm run prepush` before every push** ([lesson](lessons/run-the-prepush-check-before-pushing.md)).
  Push only when it passes; report any `SKIPPED` step (a tool missing on the machine) instead of ignoring it.
- **Name a decider only from the sender line** ([lesson](lessons/name-a-decider-only-from-the-sender-line.md)).
  Before you write that a person approved, held, lifted, overrode or decided something (a PR
  description, release notes, a ledger note, a report), copy the name from that message's
  `[from <name>]` or `[from the orchestrator, for <name>]` line, or from the ledger's requester. A
  message without one is not from "the user" your prompt names: write "unconfirmed" and ask.
- **Time the added code when the bench cannot resolve 1%** ([lesson](lessons/settle-your-own-guesses.md#when-a-measurement-cannot-resolve-it-measure-closer-to-the-change-w824-2026-10-09)). A class 3
  desync PR whose before/after runs spread wider than 1% gets the added functions timed directly on the same save,
  with the triggering case present and absent (`checklists/ffbox-desync-pr.md`, w824).
- **A CI test does not gate on the clock** ([lesson](lessons/verify-simulation-at-a-slow-hosts-frame-rate.md#a-ci-test-does-not-gate-on-the-clock-w857-2026-10-10)). A test the editmode job runs asserts no wall-clock ratio or time limit (make the benchmark `[Explicit]`, assert the structure), and a `[UnityTest]` waiting on real I/O counts seconds, not frames (w857: a 19 % flake and 422 s of a 14 minute job).
- **Read why a CI job died before re-running it** ([lesson](lessons/settle-your-own-guesses.md#read-why-a-ci-job-died-before-re-running-it-w906-2026-10-10)). A job
  cancelled at its timeout with no log at all (`BlobNotFound`) lost its runner; one with its log names the hung test
  (a watchdog prints it); "coverage file is empty" with every test green is a node child ended mid-exit. Name the
  cause before any re-run (w906: 27 coverage failures in 30 days and two lost jobs, each re-run blind).
- **Every new system runs in a test** ([lesson](lessons/verify-simulation-at-a-slow-hosts-frame-rate.md#a-new-system-runs-in-a-test-before-the-first-in-game-run-w809-2026-10-09)). Before you report a change
  that adds an `ISystem` or `SystemBase` (presentation and animation systems too), name the test that schedules it in a
  world with a matching entity. A system nobody runs throws on its first frame in a real world (w809: an aliasing error
  in a job, found by a PlayMode fixture load, not by 9,381 green tests).

## Checklists: read the one for what you are doing

- [Done](checklists/done.md): before `DONE: wNNN` or saying a request is finished: merged, every
  check the brief's Done names, the steps after the merge, the `Learned:` line, your disk leftovers removed (builds, Captures, worktrees, player slots),
  labels and ids.
- [Delete](checklists/delete.md) (w896): before any remove on a machine's disk, a clean-up above all: every path strictly inside
  the worker install folder (`$FF_WORKER_ROOT`); outside it you measure and report sizes and list what writes there, whatever
  the brief says.
- [Visual changes](checklists/visual.md)
- [UI changes](checklists/ui.md): screens, panels, tabs, HUD, layouts: a late-game save, every
  sub-view, the whole content, the classic look side by side, a real-rate clip, one written line
  per still against the requester's words, and the rest of the screen unchanged (a layout census
  before and after: no new overlap between always-on HUD blocks, no cluster drift over 2 px, every
  touched panel's colour and alpha against a classic panel; a panel the player opens may cover
  the HUD if it is on top, clickable and gives the HUD back; every HUD element the change moved, at
  1920x1080, 1280x800 and 1280x800 docked, asked for in the brief's own words, and every pin held); `Content:`, `Full content:`,
  `Style:`, `Shots:`, `Overlaps:`, `Alignment:`, `Moved:`, `Pinned:` (and `Opened panels:`) in the PR.
- [Steam Deck changes](checklists/deck.md) (w770): glyphs, Steam Input, launch resolution, Deck UI, touch: what a Deck
  tour cannot show, the cheap stand-ins, the real-Deck request to write for your orchestrator (first step: the Deck's
  Steam client and SteamOS are up to date), and the `Real Deck:` line in the PR.
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
  hold only for exceptional risk or a timing reason, and say which and when. mechanics: check `git branch --show-current` after a wait, gate `gh pr merge` on a passing check (`gh pr checks N && gh pr merge N --match-head-commit <sha>`: exit 8 is pending; w864), post the verdict only from the newest ff-agents (w807).
- [A release lands where SETLIVE says](lessons/a-release-lands-where-setlive-says.md): develop on
  `development`, master on `pre-release`; run `release-status.py`, never recall it.
- [A release is done when its notes are posted](lessons/a-release-is-done-when-its-notes-are-posted.md):
  live on its branch AND the patch notes posted as Max in #dev-patch-notes (`post_as_max`, any
  machine); a failed post stays an open step in the report, with FFBox's reason.
- [Keep rm out of long commands](lessons/keep-rm-out-of-long-commands.md): a deletion chained
  into a long command waits on a permission prompt nobody sees.
- [Text for the person to paste is plain](lessons/paste-text-is-plain.md): no code block, no
  formatting, their voice.
- [Say what an id is, every time](lessons/say-what-an-id-is.md): w293, #972, a sha or a sandbox
  name means nothing to a person; put what it is beside it, every time.
- [Lessons belong in the harness repo, written before DONE](lessons/lessons-belong-in-the-harness-repo.md):
  every DONE carries `Learned:`; a correction or reopen gets a check; the strongest home first (tool,
  checklist, skill, the doc beside the code); a second correction of a kind is filed by the
  orchestrator (w741: five rounds of Deck UI corrections before a check changed). A GitHub 403 on a token for a
  permission or repository not on ff-factory's `shared/githubRequirements.ts` is added there in a PR, so the portal's
  banner asks for it (w904).
- [Verify simulation at a slow host's frame rate](lessons/verify-simulation-at-a-slow-hosts-frame-rate.md):
  per-frame code writes no simulation state; prove a move with a frame-without-heartbeat test and a
  multiplayer run whose host is held near 20 fps (w342/w356: a Steam Deck host forked alone).
- [Name a decider only from the sender line](lessons/name-a-decider-only-from-the-sender-line.md):
  an approval, hold or decision gets the name on its message's `[from …]` line or the ledger's
  requester; none means "unconfirmed" and ask (w389: a bare message became "Release hold lifted (Ben)").
- [Check the other system's live config](lessons/check-the-other-systems-live-config.md): a tool's
  sentence about what another system does is a guess until that system's own config says so (w412:
  "automatic investigations are not built yet" while FFBox's `intake.auto` was on); what FF Factory itself did
  comes from `portal_logs`, not from the code (w920).
- [Check who uses a shared shader or material](lessons/check-who-uses-a-shared-asset.md): run the
  game repo's `scripts/asset_usage.py` before the edit; more users than the target means a new
  shader or material for it, or a built-player before/after of every user; the PR's `## Used by`
  lists them and `pr_evidence.py` and CI fail without it (w410: one sprite-shader edit for the
  Alt-view icons darkened every range ring in Build 77).
- [Check every kind of object shared presentation draws](lessons/check-every-kind-of-object-shared-presentation-draws.md):
  a change to the selection boxes, highlights, icons or panels is verified on every kind of object
  they draw, spinning and moving ones included, and a discriminating component is counted against
  every archetype that carries it (w586: w453 turned every `Placeable`'s box with its target, so
  comet fragments' boxes spun from 0.50.0.80).
- [Verify UI with full content, like a player](lessons/verify-ui-with-full-content-like-a-player.md):
  every screen and sub-view in a late-game save, whole, on the classic look, still in a real-rate
  clip, each still checked against the requester's words (w718: the w644 hub, #1251, passed a tour
  of "opens, fits, 9 px" stills; on Ben's Deck it was navy, Crafting one row, no tech grid; w764: ten photos of
  a real Deck found eight faults the tour's census had no count for, so a player's photos are tests; w770: a Deck-facing change is "verified on a real Deck" (who, Steam client and SteamOS
  versions, what they saw) or "not verified on a real Deck", never a bare done on a tour, and `pr_evidence.py` fails the PR
  without a `Real Deck:` line, [checklist](checklists/deck.md): w684's glyph fix passed a tour and Ben's Deck showed none,
  w767's resolution bug is invisible to a tour that forces its size).
- [A UI change leaves the rest of the screen as it was](lessons/a-ui-change-leaves-the-rest-of-the-screen-as-it-was.md):
  a layout census before and after with the whole HUD up: no new overlap between always-on HUD
  blocks (a panel the player opens may cover the HUD: Ben, w742), no anchored cluster
  drifting over 2 px, every touched panel measured against a classic one; run the released
  `pr_evidence.py` (w733: the minimap buttons drifted, a slide-out covered the hotbar, and #1272's
  navy passed a check older than the release that would have failed it); and nothing moves that the
  brief did not ask to move, every move listed and asked for in the brief's own words (w826: #1280
  pushed the objectives card under the Station strip, #1282 moved the Station Info box to the top left;
  Ben: "i didnt tell you to move that"); w894: the hard rule, no "justified" moves, quotes checked against the
  brief, the docked layout censused, and the places Ben fixed pinned (`unity-ui/hud-pins.json`) because the dock had
  kept Station Info and the hover card top left since w772 and every parent-based diff called that normal.
- [Measure against what the player sees](lessons/measure-against-what-the-player-sees.md): a
  placement metric is checked against the drawn surface or outline, computed independently of the
  code under test, never against the code's own answer (w587: w176's impacts scored 0.0 u against
  the simulated hit point while they landed inside the hull).
- [Say DONE per request](lessons/say-done-per-request.md): end a report with `DONE: wNNN` only when
  every step of the request is finished, post-merge steps included; answer a wrap-up or "Is it
  done?" with DONE or what is left (w419: w342 stayed open with its work done).
- [A fix PR names its Discord report](lessons/a-fix-pr-names-its-discord-report.md): a
  `Discord: <thread or message link>` line before it merges, and `RESOLVED: already fixed by PR #N`;
  FFBox tells the reporter from those only (w436 / #1076 went untold).
- [A fix names its player report](lessons/a-fix-names-its-player-report.md): a `Report: <id>`
  line in the PR, or the id as a request subject; a brief's ids claim nothing, and FFBox keeps the
  report open (w414 / #1064 left two Build 76 crash reports NEEDS-INFO).
- [Workers do not clean up; the harness does](lessons/clean-up-after-yourself.md): leave builds, clones, logs and scratch in `$TMPDIR`
  (the daemon sweeps it when your process ends, w913: "Random clean up commands take a lot of approvals"); no rm, no
  `player_slots.py prune`, no clean-up step before DONE; a mid-task `rm -rf` under `$TMPDIR` needs no approval; low disk is
  fixed by the harness or by filed clean-up work, never by asking a person (w596/w626).
  Same lesson, deletes (w896): only inside the machine's worker install folder (`$FF_WORKER_ROOT`); outside it you measure, report
  sizes and list what makes FF Factory write there, whatever the brief says (w876 cleared dotnet temp, the Unity Hub installer,
  Temp, test output and old transcripts on LothDesktop's C:; lothsahn: "in general we should only be clearing data in the
  install folder for the worker"; [checklist](checklists/delete.md)).
  Same lesson, Unity slots: your own `-batchmode` builds end before DONE (`unity-slot status`); a start refused for a
  stuck batch holder gets `unity clear_batch`, not a multi-hour wait or a request to end it by hand (w791: two builds
  held slots for hours).
- [No human-time estimates](lessons/no-human-time-estimates.md): size work by scope, or by a
  measured agent time from a named comparable run, never in human days or weeks (w545: the Steam
  Deck report's "1–2 weeks" and "weeks to months"; Ben: "stop giving human time estimates").

- [A wait on a person is declared, not polled](lessons/a-person-wait-is-declared-not-polled.md): when only a
  person can move you on, call `waiting_on_person` and end the turn naming who and what; a `wake_me` check-in
  shows the request Working (w665: Working for 10 h while it waited for Ben to reboot the m3). First check a
  person is needed: never hand a person a step the ops worker or ssh can do, an installer rerun included
  (w855: the dispatcher asked Ben to rerun biscuit's installer for w847).

## Adding a lesson: before every DONE

Every request ends with a `Learned:` line in the DONE report: the file or PR you added, or
`nothing new` (FF Factory's ledger refuses a DONE without it). Something was learned when a person
corrected you or reopened the request (always: add the check that would have caught it), a check
failed on you before it passed or you redid a step three times, `git log --since=14.days` on your
files shows another fix of the same kind, or you found a fact a future agent would have needed.

1. **Search first** and extend an entry rather than add one.
2. **The strongest home**: a tool check with the failing case as a fixture, then a checklist line,
   then the task's skill, then the doc beside the code in the game repo; a lesson here only for the
   dated why. Lessons about one system go to `project-memory`, marketing to ff-marketing.
3. **Quote the person**, never a paraphrase. Their latest words beat a lesson or a check: follow
   them and fix the lesson.
4. **Through `publish-skills`**, as a pull request. CI caps this list at 26: a new lesson merges or
   retires one. A rule a tool now enforces shrinks to its why.

A person's **second correction of the same kind** is a harness bug: their orchestrator tallies
corrections by kind and files the harness work on the second; a worker that sees it adds the check
with the fix. The rule, the homes and the Deck UI story: [lessons belong in the harness
repo](lessons/lessons-belong-in-the-harness-repo.md). The design and its sources:
[design-w741.md](design-w741.md).

The reasoning behind this skill, the incident it came from and the prior art: [design.md](design.md).
The week's cases replayed against it: [replay-2026-10-02.md](replay-2026-10-02.md).
