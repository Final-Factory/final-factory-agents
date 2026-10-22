---
name: evidence-gate
description: "Before any consequential action (spending money, publishing, a live setting, a release, merging a simulation or player-visible change, deleting, reporting a fix as done) or recommending one: list the choices, say what each rests on (measured, sourced or guess), settle your guesses, name how it could fail, then proceed. Holds the lessons, the checklists (done, delete, visual, UI, Deck, merge, release, desync PR) and pr_evidence.py. Use before acting on anything unverified, when writing a brief or report with numbers, and after any miss (add a lesson)."
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
pull request. In the game repo, "CI is green" means its required `Test in editmode` check, which on a pull request now runs only the compile, the
tests the change touches and one smoke PlayMode test; the whole suite runs after the merge in
`master-batch.yml`, and a pull request that breaks it comes back as an urgent revert request (w1180,
the game repo's `Documentation/Merge-Queue.md`). Don't stop at an open PR waiting for the person. Hold one only for exceptional risk
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

**Options and mocks too** (Ben, w1429, the fifth correction: "getting extremely worried you guys moved the fucking station
controls panel when i told you not to twelve times"; [lesson](lessons/a-ui-change-leaves-the-rest-of-the-screen-as-it-was.md#options-and-mocks-move-only-what-the-person-named-w1429-2026-10-17)). An
option or mock may move only the elements the person named. When the named change does not fit, report the conflict and
offer only options that keep every unnamed element in place, or ask; never offer one that moves it. `ui_layout.py
options` against master's census puts each option IN or OUT before the round goes out, and the critic fails an option
with an unnamed move (item 32).

## No UI still reaches a person before the design gate

Ben, 2026-10-16: "you make bad UI mistakes constantly". The gate, at the top of the [UI checklist](checklists/ui.md):
1. Build from the game's own components and colours (the game repo's `docs/UI-Style.md`).
2. Grade every still yourself with the unity-ui `design-rubric.md` (`Eye:`).
3. Measure it against the before with `ui_look.py colour` and `ui_layout.py shape` (`Colour:`, `Shape:`).
4. Have a **fresh** `ff-agents:ui-critic` grade the pack `ui_look.py pack` builds (`Critic:`), and fix or answer each
   broken or ugly finding. A STANDING one is fixed or filed with its wNNN, never "handed on", and a coverage gap the
   critic names that is the person's own case gets its stills
   ([lesson](lessons/verify-ui-with-full-content-like-a-player.md#a-standing-finding-is-filed-with-its-wnnn-or-fixed-and-the-critics-coverage-gap-is-shot-w1546-2026-10-19)).

"Same both sides", a clean census and "Looked: yes" are not that answer. A redesign goes out as 2-3 clearly different
options built from the game's best existing dialogs (Ben, w1296: "reuse components when you can damnit"). Orchestrators
look first and relay only with the critic's report (FF Factory `read_rules ui`). Items 27-31;
[lesson](lessons/verify-ui-with-full-content-like-a-player.md#a-fresh-critic-not-the-author-judges-the-design-w1399-2026-10-16).

## Reports and briefs

- Label each number and recommendation **measured**, **sourced** or **guess**. Say what you saw,
  not what a title, a measurement table or a tool verdict implies.
- A brief for consequential work lists the decisions the work must settle, and says the worker
  settles its own guesses.
- When you pass on someone's report, keep its labels. A guess never becomes a recommendation on
  the way up.
- **A crash inside a GPU driver is not "nothing to fix" yet** ([lesson](lessons/settle-your-own-guesses.md#a-crash-inside-a-gpu-driver-is-not-nothing-to-fix-until-four-checks-are-done-w956-2026-10-13)).
  Before a NOT-A-BUG verdict on a crash with only driver frames, give the driver's date and how far behind
  current it is (vendor release notes), the CPU from the dump (stream 7; Intel family 6 model 0xB7/0xBF is
  Raptor Lake), the game step that fed the driver and how long it runs, and a lever that keeps that player
  booting or why there is none (w956: Ben reopened "driver, nothing to fix").
- **A claim about what another system does comes from that system** ([lesson](lessons/check-the-other-systems-live-config.md)).
  Before you relay "X is not built", "nothing will investigate this" or "that is off" from one
  system's tool about another, read the other system's live config or state (for FFBox,
  `ffbox_activity show config` / `show signatures`) and quote the key and value, or say unknown.
  For what FF Factory itself did (a deploy, a clean-up, an update, a restart), read the portal's own logs with
  `mcp__machine__portal_logs` (w920) and name the source and window; never infer it from the code.
- **List environment variables by name, never their values** ([lesson](../project-memory/memories/list-env-by-name-never-values.md)).
  `env | cut -d= -f1 | grep -i <word>`, or `printenv NAME | wc -c` to see a value is set; never `env | grep` and a sed
  that redacts what you thought of (w1664: a filter on TOKEN printed the vault's FFSTEAM_PASSWORD into a transcript).
- **Compile-check before you start the editor after a revert or a delete** ([lesson](../project-memory/memories/compile-check-before-you-start-the-editor.md)).
  Change code with the editor running and `refresh_unity`. With it stopped, `git grep` every name you removed (tests
  too) and run editor-ops' offline compile check before `unity start`/`restart`: a compile error on disk at boot puts
  the editor on the "Enter Safe Mode?" prompt with no bridge (w1470, w1495).
- **Research the route before you say "can't" or "you do it"** ([lesson](lessons/research-the-route-before-you-say-cant.md)).
  Before you send a person "I can't", "no agent can", "you can ... yourself" or "<Name> needs to", research the route
  (the tool's own docs, the skills, the machines and the sessions already signed in on them, the tools you and the
  workers have), then try it or file it for an agent whose tools reach it; an orchestrator's own limits are not the
  system's. Only a concrete blocker reaches the person, with its evidence and the smallest step only they can take
  (their own login, password or 2FA code, an approval). Ben corrected this twice: w935 (Unity on his m5: "You can close
  Unity") and w1287 (the Factions design doc in Claude Design: "I already asked for this").
- **Drive only the windows you opened** ([lesson](lessons/research-the-route-before-you-say-cant.md#drive-only-the-windows-you-opened-w1287-2026-10-14)). Before any
  computer-use click or key on a person's computer, name the app and the window id you opened in this request and pass
  that window to every call; never click, type or scroll in a window they had open (their Claude desktop app, chat,
  editor, terminal, dashboard), even when it holds the signed-in session you need: open your own browser window or use
  Claude Code's own tool. Touched one by mistake: put it back and report each click (w1287; Ben: "WHY IS IT POKING
  AROUND IN MY CLAUDE DESKTOP APP").
- **Say what every id is, every time** ([lesson](lessons/say-what-an-id-is.md)). Before you send
  anything a person reads, scan it for request ids (w293), PR numbers (#972), commits, worker or
  session ids and sandbox names: each one gets its plain-English words beside it, on every
  appearance, not only the first.
- **Review media goes inline, never as a bare path** ([lesson](lessons/visual-fixes-are-verified-by-looking.md#review-media-goes-inline-never-as-a-bare-path-w1384)). Before you
  send anything a person reads, scan it for review paths (`/srv/fff/review/…`), folders, wildcards and
  `.mp4`/`.png`/`.jpg` names: each still and clip is its own `![name](<absolute path>)` line, a folder is each of its
  files (newest first, never `.preview/`). Ben, 2026-10-15: "Stop giving me paths to videos and inline the videos like
  you should be doing and I've reminded you as such like 100 times" (w1384).
- **No human-time estimates** ([lesson](lessons/no-human-time-estimates.md)). Before you send a
  report, plan or TL;DR, scan it for sizes in days, weeks, months or sprints ("1–2 weeks",
  "weeks to months"). Rewrite each as scope (files and systems touched, surfaces, risk,
  dependencies) or as a measured agent wall-clock time or cost from a named comparable run,
  labelled measured. No comparable run: scope only.
- **On ff-factory, `npm run prepush` before every push** ([lesson](lessons/merge-your-own-pr.md#before-the-push-the-repos-own-pre-push-check-ff-factory-w924-2026-10-10)).
  Push only when it passes; report any `SKIPPED` step (a tool missing on the machine) instead of ignoring it.
- **Ask for the go-live moment before big content reaches a Steam branch** ([lesson](lessons/ask-before-content-goes-live.md)).
  Before a build, a bump PR, or a brief or plan that makes major new content live on any Steam branch (1.0, a
  feature toggle on by default, an open beta), name the person's go for that moment in their own words; an
  agreed plan says where, not when, so without it stop and ask. Routine hotfix builds don't need it (w1453:
  1.0.0.0 went live on `development` on w1436's plan; Ben: "You should have asked me I need to do a steam event
  and stuff"; release checklist item 1b).
- **Name a decider only from the sender line** ([lesson](lessons/name-a-decider-only-from-the-sender-line.md)).
  Before you write that a person approved, held, lifted, overrode or decided something (a PR
  description, release notes, a ledger note, a report), copy the name from that message's
  `[from <name>]` or `[from the orchestrator, for <name>]` line, or from the ledger's requester. A
  message without one is not from "the user" your prompt names: write "unconfirmed" and ask.
- **Time the added code when the bench cannot resolve 1%** ([lesson](lessons/settle-your-own-guesses.md#when-a-measurement-cannot-resolve-it-measure-closer-to-the-change-w824-2026-10-09)). A class 3
  desync PR whose before/after runs spread wider than 1% gets the added functions timed directly on the same save,
  with the triggering case present and absent (`checklists/ffbox-desync-pr.md`, w824).
- **A speed-up is one build, switched off and on, back to back** ([lesson](lessons/settle-your-own-guesses.md#a-speed-up-is-one-build-switched-off-and-on-back-to-back-w1069-2026-10-13)).
- **An A/B on one machine: prove the action happened, run both builds at once and swap the CPU sets** ([lesson](lessons/settle-your-own-guesses.md#an-ab-on-one-machine-check-the-thing-happened-and-run-both-builds-at-once-w1329-2026-10-15)).
  Before you report a performance gain, measure the same build with the change switched off and on, back to back on
  the same machine, and check that a system the change does not touch reads the same in both (within about 10%); a
  run from earlier is not a baseline on a shared machine (w1069: 2.3x against an earlier run, 20% against the switch).
  Before each leg, nothing of yours still runs: `TaskStop` does not end the loop script or its player, so list the processes and
  `ff-leftovers list` first ([w1258](lessons/settle-your-own-guesses.md#before-every-leg-nothing-of-yours-is-still-running-w1258-2026-10-14)).
- **An equivalence test of a pruned search puts a tie on each bound** ([lesson](lessons/settle-your-own-guesses.md#an-equivalence-test-of-a-pruned-search-puts-a-tie-on-each-bound-and-fails-on-the-flip-w1069-2026-10-13)).
  Before you call an index or pruned search "the same pick as the full scan", have a case with a tie exactly on each
  bound it stops or skips on, and see the test go RED with that bound's `>` flipped to `>=` (w1069: random worlds all
  passed the flip).
- **A CI test does not gate on the clock** ([lesson](lessons/verify-simulation-at-a-slow-hosts-frame-rate.md#a-ci-test-does-not-gate-on-the-clock-w857-2026-10-10)). A test the editmode job runs asserts no wall-clock ratio or time limit (move the timing to a `[Category("Performance")]` test, assert the structure), and a `[UnityTest]` waiting on real I/O counts seconds, not frames (w857: a 19 % flake and 422 s of a 14 minute job).
- **A determinism pair is any two free machines; a cross-OS pair only when the change can differ by platform** ([lesson](lessons/verify-simulation-at-a-slow-hosts-frame-rate.md#a-determinism-pair-is-any-two-free-machines-a-cross-os-pair-only-when-the-change-can-differ-by-platform-w1692-2026-10-21)).
  Two players on whatever machines are free, any OS; a Mac host against a Windows or Linux client only for float or
  math-library use in the simulation, Burst or IL2CPP codegen-sensitive code, platform APIs or file paths, the desync
  hash or its capture, or a desync reported only across OSes. The report says why the pair did or did not need it (lothsahn, w1692).
- **A timing test is tagged Performance and checks nothing else** ([lesson](lessons/verify-simulation-at-a-slow-hosts-frame-rate.md#a-timing-test-is-tagged-performance-and-checks-nothing-else-w1690-2026-10-21)). A game test that asserts on
  timing (ms, frame time, throughput, a speed ceiling or ratio) carries `[Category("Performance")]` and asserts nothing
  functional; a functional test never carries it, since every CI lane leaves the category out. Performance tests run in no
  CI: locally, against a baseline from the same machine. A mis-tagged or mixed test you meet, you fix (split a mixed one).
  Never loosen a timing threshold to pass CI (lothsahn, w1690).
- **Read why a CI job died before re-running it** ([lesson](lessons/settle-your-own-guesses.md#read-why-a-ci-job-died-before-re-running-it-w906-2026-10-10)). A job
  cancelled at its timeout with no log at all (`BlobNotFound`) lost its runner; one with its log names the hung test
  (a watchdog prints it); "coverage file is empty" with every test green is a node child ended mid-exit. Name the
  cause before any re-run (w906: 27 coverage failures in 30 days and two lost jobs, each re-run blind).
- **Bulk GitHub reads take the cheap path and stay inside the shared budget** ([lesson](lessons/settle-your-own-guesses.md#read-github-history-the-cheap-way-well-inside-the-shared-budget-w1175-2026-10-13)).
  Before bulk GitHub API reads (CI history, many runs or logs), use the cheap path (one day per page, GraphQL batches,
  check-run annotations instead of log downloads), cap the call count, and check the budget of the token you actually
  spend (w1173 and w1175 spent the account's ~5,000 calls an hour together on 2026-10-13 and stalled CI for everyone).
- **Every new system runs in a test** ([lesson](lessons/verify-simulation-at-a-slow-hosts-frame-rate.md#a-new-system-runs-in-a-test-before-the-first-in-game-run-w809-2026-10-09)). Before you report a change
  that adds an `ISystem` or `SystemBase` (presentation and animation systems too), name the test that schedules it in a
  world with a matching entity. A system nobody runs throws on its first frame in a real world (w809: an aliasing error
  in a job, found by a PlayMode fixture load, not by 9,381 green tests).

## Checklists: read the one for what you are doing

- [Done](checklists/done.md): before `DONE: wNNN` or saying a request is finished: merged, every
  check the brief's Done names, the steps after the merge, the `Learned:` line, your disk leftovers removed (builds, Captures, worktrees, player slots),
  labels and ids, and every quote copied from its source (`quote_check.py`, w1399).
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
- [Balance changes](checklists/balance.md) (w1440): enemy, combat, spawn, economy or research numbers: the game repo's
  `BAL-*` stages on players of the base and the branch, `balance_lane.py compare` in a `## Balance` section (`Stages:`,
  the table, `Flags:`, `Baseline:`), or `No curve change: <why>`; `pr_evidence.py` fails an enemy, combat or spawn change
  without it (Build 108's late-game raids, w1439).
- [Releases](checklists/release.md)
- [Timed bench runs](checklists/bench.md) (w1628): before taking a shared machine's bench lock: the shortest run that
  answers the question, the fewest rounds, early stop on and a decision once the signal is clear, at most one hour per
  exclusive hold, the exclusive ticket only for timed numbers (`bench_lock --shared` for untimed work, nothing for a
  build), nothing under the lock but the leg, and the lock time in the report.
- [FFBox desync PRs](checklists/ffbox-desync-pr.md) (Lothsahn's standing policy, 2026-10-04): classify
  1 report generation only, 2 a game desync fix, 3 capture during play; tests, a 2-peer red/green
  check for 2, a before/after tick and frame measurement for 3 (under 1% merges, above escalates
  through the intake with `PERF-ESCALATION`).
- Ads and outreach live in the ff-marketing repo: `lessons/ads.md` and `lessons/outreach.md`,
  enforced by `scripts/ads/ffads lint`.

## Lessons: the rules this team paid for

One file each under `lessons/`: the rule, why (the incident, dated), how to apply.

- [Hold the bench lock as briefly as the question allows](lessons/settle-your-own-guesses.md#hold-the-bench-lock-as-briefly-as-the-question-allows-w1628-2026-10-20): lothsahn,
  2026-10-20: "A benchmark with 90% fidelity that runs twice as fast as better one is likely the right choice." The
  shortest run that answers the question, early stop, shared tickets for untimed work (w1628: BEAST held 15.5 of 16 h);
  "Get them all to shorten their plans a lot", "if they have sufficient signal, just make a decision", and no exclusive
  hold over 1 hour.
- [Research the decision, not the topic](lessons/research-the-decision-not-the-topic.md): the
  Reddit caps came from a topic survey; nobody asked what bid wins US auctions. Label every basis.
- [Settle your own guesses](lessons/settle-your-own-guesses.md): Ben wants agents mostly
  autonomous; he confirms money, reserved actions and real forks, and is not a way out of research.
- [Look early, by breakdown, against a written expectation](lessons/look-early-by-breakdown.md):
  four checks of totals said "nothing wrong"; the country table at 21.6 hours showed the failure.
- [A visual fix is verified by looking](lessons/visual-fixes-are-verified-by-looking.md): a built
  player, a clip that contains the event, the intended look in the person's words; `watch_video`
  is a second opinion; also hunt for what should not be there (ghosts, leftovers, overlaps, z-order) before saying "matches" ([section](lessons/visual-fixes-are-verified-by-looking.md#hunt-for-what-should-not-be-there-w895-w1015), w895, w1015); new art matches the art language: two solid main colours + one bright bloomy HDR accent, a highlight is the object's own emissive/rim light, never a world-space halo or UI-like indicator, compared side by side with a named reference asset ([section](lessons/visual-fixes-are-verified-by-looking.md#new-art-matches-final-factorys-art-language-w1066-w1241), checklist 5c; w1066, w1241). A glow is measured against a powered mass driver in the same built-player frame with the game repo's `scripts/feel/glow_compare.py` before it goes to the requester ([section](lessons/visual-fixes-are-verified-by-looking.md#a-glow-is-measured-against-a-glowing-reference-in-the-same-frame-w1323), checklist 5d; w1323). Every "it's gone" or "it happens" ("no z-fight", "ships spaghettify") names a 1:1 crop or a slowed segment of that moment, over every surface the effect overlaps (terrain, structures, other VFX), and the fresh critic gets it as a question; `pr_evidence.py` checks the `Close-ups:` and `Surfaces:` lines, `--note` a review note before `publish_review` ([section](lessons/visual-fixes-are-verified-by-looking.md#every-its-gone-is-shown-close-up-against-every-surface-w1567), checklist 5g; w1470, w1567). A transition ("stretches into", "swallowed", "stays lit as itself") is every frame of it, cropped on the object, until its end state, from `transition_strip.py`, and a second opinion's "disappears" is cleared only by that strip, never a 0.2 s sheet ([section](lessons/visual-fixes-are-verified-by-looking.md#a-transition-is-stepped-every-frame-on-the-object-and-it-disappears-is-cleared-only-that-way-w1686), checklist 5h; w1470, the Guardian vanishing mid-swallow, w1686).
- [Hero art is creative and detailed](lessons/visual-fixes-are-verified-by-looking.md#hero-art-is-creative-detailed-and-different-w1470-w1466): a new model or hero VFX
  (w1470 Singularity Lance, w1466 Urso Ballista; Ben: "this is the end game weapon that needs to look really cool ...
  be creative with this", "we need high quality models") first comes as 2 or 3 different concepts, a literal object
  (bow, disc) is reinterpreted for space, the detail is compared in one still with our best models of the class, a new
  weapon's projectile and impact are compared with the Railgun's and Plasma Bolt's (reuse called out), and the verdict
  says what makes it distinctive (checklist 5e). A third correction (w1475 shield effect: "more subtle and tighter to the
  ship itself ... be creative and be more high quality (but performant)") made it a tool check: `pr_evidence.py` fails a
  PR that adds a model or effect art without a filled `Hero art:` line (concepts and pick, detail comparison, how it
  differs, distinct, measured cost; merge checklist), and checklist 5f is the reviewer's read; publish the concepts
  before any build-quality clip (w1497).
- [No merge before the review](lessons/no-merge-before-the-review.md): "pending" is not done.
- [Merge your own pull request](lessons/merge-your-own-pr.md): verified and green means merge;
  hold only for exceptional risk or a timing reason, and say which and when. mechanics: check `git branch --show-current` after a wait, gate `gh pr merge` on a passing check (`gh pr checks N && gh pr merge N --match-head-commit <sha>`: exit 8 is pending; w864; in a worker `ff-pr merge`, one call, w1478), post the verdict only from the newest ff-agents (w807); a red check that is not your change, and `not our ref` at checkout ([section](lessons/merge-your-own-pr.md#a-red-check-that-is-not-your-change-read-the-failing-test-then-the-cause-w1337-2026-10-15), w1337).
- [A release lands where SETLIVE says](lessons/a-release-lands-where-setlive-says.md): a master bump
  on `development`, nothing sets `pre-release` or the default; run `release-status.py`, never recall it.
- [Ask before content goes live](lessons/ask-before-content-goes-live.md): a build that makes major new
  content live on any Steam branch (1.0, a toggle on by default, an open beta) waits for the person's go for
  that moment, even on an agreed plan; a brief or PR that changes what a branch serves by default names that
  go (w1453: 1.0.0.0 reached `development` before Ben's Steam event; release checklist 1b).
- [A release is done when its notes are posted](lessons/a-release-is-done-when-its-notes-are-posted.md):
  live on its branch AND the patch notes posted as Max in #dev-patch-notes (`post_as_max`, any
  machine); a failed post stays an open step in the report, with FFBox's reason. The notes are for
  players only (features, fixes, balance, performance, platform support), never branches, the dev flow,
  CI, merge queue, FFBox or agents (Build 101, w1190); `release_notes_lint.py` runs before the bump and
  before `post_as_max`. A line about a change behind a feature toggle never ships either (every toggle is
  off for a release player: Build 104's "Mobile stations take their bots and barges with them", w1242):
  `release_notes_check.py <notes> --repo <game clone> --range <prev>..<release>` flags both kinds and runs
  before the bump and before `post_as_max` ([section](lessons/a-release-is-done-when-its-notes-are-posted.md#patch-notes-list-only-what-players-can-use-build-104-w1242)).
- [Keep rm out of long commands](lessons/clean-up-after-yourself.md#keep-rm-out-of-long-commands-w63-w194-w1097): a deletion chained
  into a long command waits on a permission prompt nobody sees; in bypass mode only an `rm` of
  `$VAR/*` or `$VAR/{a,b}` (or a critical path) asks (measured, w1097). A new folder per run,
  multi-step logic in a script file in `$TMPDIR`, the game's settings and saves through
  `scripts/game_data.py`.
- [Text for the person to paste is plain](lessons/paste-text-is-plain.md): no code block, no
  formatting, their voice.
- [Review media goes inline](lessons/visual-fixes-are-verified-by-looking.md#review-media-goes-inline-never-as-a-bare-path-w1384): every still and clip as `![name](<absolute path>)`,
  a folder as its files, never a bare path (w1384).
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
- [Judge every UI still by eye](lessons/verify-ui-with-full-content-like-a-player.md#judge-every-still-by-eye-before-the-person-sees-it-w1386-w1296-2026-10-16): before a still goes to a person, one line
  per still on whether anything looks broken or poor (stretched controls, mostly empty windows, overlapping labels, text
  dumps), apart from every before/after comparison; `ui_layout.py shape` measures the first two and walls of text; a
  redesign goes out as 2-3 options built from the game's best dialogs (w1386: a 485x23 switch passed as "Same both
  sides"; w1296: round 3 nudged spacing; Ben: "the light panel is really messed up obviously", "looks terrible. you can
  do better", "reuse components when you can damnit"; checklist ui.md 27-29). And a fresh critic, never the author, grades
  every still from a pack of crops, reference panels and the person's words before a person sees it, with `ui_look.py
  colour` clean against the before (w1399: three rejected screens all said "Looked: yes"; round 2's see-through chips drawn
  delta E 13.6 off their twins in a plain row; UI alpha blends in linear space here; checklist ui.md 30-31).
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
- [Options move only what the person named](lessons/a-ui-change-leaves-the-rest-of-the-screen-as-it-was.md#options-and-mocks-move-only-what-the-person-named-w1429-2026-10-17): the hard rule holds
  for every option and mock offered, not only the pull request (w1429: on w1386 the round-3 options A, B and C each moved
  the station controls panel after Ben said "keep the station controls where they were"); `ui_layout.py options` against
  master's census drops every option with an unnamed move, and the ui-critic fails it (checklist item 32).
- [Window overlaps are measured by the tool, not by eye](lessons/a-ui-change-leaves-the-rest-of-the-screen-as-it-was.md#window-overlaps-are-measured-by-the-tool-not-by-eye-w981-2026-10-11): `ui_layout.py
  overlaps` counted only always-on HUD blocks, so the Station strip standing 11 px over the Player Inventory (w961, #1444;
  22 to 45 px on develop with w978) read 0 and a worker measured rects by hand (w981); now every open window against the
  HUD and each other is the `Window overlaps:` line, allowed only by a quoted `hud-clusters.json` `windowOverlaps` entry,
  and `pr_evidence.py` fails a new or kept one ([UI checklist](checklists/ui.md), item 24).
- [Text is covered by its drawn bounds, not its box](lessons/a-ui-change-leaves-the-rest-of-the-screen-as-it-was.md#text-is-covered-by-its-drawn-bounds-not-its-box-w727-2026-10-11): the Technology tab's "Excess Research 0.0" label ran half under the hub's tab bar and every census check read 0, because the census held RectTransform boxes only (w727, #1291); now the census records `textRect` and `ui_layout.py covered-text` flags a text of an opened screen under an opaque element (checklist item 26).
- [Measure against what the player sees](lessons/measure-against-what-the-player-sees.md): a
  placement metric is checked against the drawn surface or outline, computed independently of the
  code under test, never against the code's own answer (w587: w176's impacts scored 0.0 u against
  the simulated hit point while they landed inside the hull).
- [Say DONE per request](lessons/say-done-per-request.md): end a report with `DONE: wNNN` only when
  every step of the request is finished, post-merge steps included; answer a wrap-up or "Is it
  done?" with DONE or what is left (w419: w342 stayed open with its work done).
- [A fix PR names its reports](lessons/a-fix-pr-names-its-reports.md): a
  `Discord: <thread or message link>` line before it merges, and `RESOLVED: already fixed by PR #N`;
  FFBox tells the reporter from those only (w436 / #1076 went untold). And a `Report: <id>` line per
  player crash or desync report it fixes, or the id as a request subject; a brief's ids claim nothing,
  and FFBox keeps the report open (w414 / #1064 left two Build 76 crash reports NEEDS-INFO).
- [A crash inside a GPU driver is not "nothing to fix"](lessons/settle-your-own-guesses.md#a-crash-inside-a-gpu-driver-is-not-nothing-to-fix-until-four-checks-are-done-w956-2026-10-13): date the
  driver, read the CPU from the dump, measure the game step that fed it, look for a guard (w956).
- [Listeners start from a stable path or bind loopback; a clip is checked for system dialogs](lessons/listeners-stable-paths-or-loopback.md):
  bind what you start to 127.0.0.1, take node from PATH (the root's `tools\node`), never a runtime unpacked into
  `$TMPDIR`, run players only from their slot (`player_slots.py firewall` names a missing rule), and look at a frame of
  every clip for a firewall, UAC or crash dialog before publishing it (w1742: node copies in temp folders prompted on
  lothdesktop; a slot2-0 prompt covered all 12 of w1722's clips on BEAST).
- [Workers do not clean up; the harness does](lessons/clean-up-after-yourself.md): leave builds, clones, logs and scratch in `$TMPDIR`
  (the daemon sweeps it once no request waits for you, not on a pause or a wait for CI, w913 and w1097: "Random clean up commands take a lot of approvals"); no rm, no
  `player_slots.py prune`, no clean-up step before DONE, and no rm to reuse a folder: each test leg writes to a new
  `$TMPDIR/<leg>-<timestamp>` (w1097); only when the disk is short mid-task, an `rm -rf` under `$TMPDIR`; low disk is
  fixed by the harness or by filed clean-up work, never by asking a person (w596/w626).
  Measure Windows folders with robocopy `/L`, never Git Bash `du`, and look for your own tool processes that a stopped shell left running ([section](lessons/clean-up-after-yourself.md#measure-windows-folders-with-robocopy-l-not-git-bash-du-w1561), w1561).
  Same lesson, deletes (w896): only inside the machine's worker install folder (`$FF_WORKER_ROOT`); outside it you measure, report
  sizes and list what makes FF Factory write there, whatever the brief says (w876 cleared dotnet temp, the Unity Hub installer,
  Temp, test output and old transcripts on LothDesktop's C:; lothsahn: "in general we should only be clearing data in the
  install folder for the worker"; [checklist](checklists/delete.md)).
  And (w1379): a clean-up deletes only what `ff-leftovers folders` marks DELETE (closed requests, orphans); the temp, build and review
  folders of a worker whose request is open, stalled or paused stay, running or not, and a brief's list of live workers is not the ledger
  (w1374 deleted stopped worker a735f37c's builds and clips while its request w1332 was stalled; [the rule](lessons/clean-up-after-yourself.md#a-clean-up-never-takes-the-folders-of-a-request-that-has-not-closed-w1379)).
  And (w1387): a DELETE row is not a go for a folder holding a git clone with uncommitted, unpushed or stashed work: check its git state or
  the portal's clean-up log ("kept for a person") first (w1385 deleted two such clones the sweeps were keeping; [the rule](lessons/clean-up-after-yourself.md#a-delete-row-is-not-a-go-for-a-folder-that-holds-a-git-clone-with-work-w1387)).
  Same lesson, Unity slots: your own `-batchmode` builds end before DONE (`unity-slot status`); a start refused for a
  stuck batch holder gets `unity clear_batch`, not a multi-hour wait or a request to end it by hand (w791: two builds
  held slots for hours).
- [No human-time estimates](lessons/no-human-time-estimates.md): size work by scope, or by a
  measured agent time from a named comparable run, never in human days or weeks (w545: the Steam
  Deck report's "1–2 weeks" and "weeks to months"; Ben: "stop giving human time estimates").

- [A wait on a person is declared, not polled](lessons/a-person-wait-is-declared-not-polled.md): when only a
  person can move you on, call `waiting_on_person` and end the turn naming who and what; a `wake_me` check-in
  shows the request Working (w665: Working for 10 h while it waited for Ben to reboot the m3). First check a
  person is needed: never hand a person a step you, the ops worker or ssh can do, an installer rerun included
  (w855: the dispatcher asked Ben to rerun biscuit's installer for w847) and Unity closed, opened or reopened, git
  commands and file copies (w935: a worker told Ben to close Unity on his m5 main clone; Ben: "You can close Unity").
- [Research the route before you say "can't"](lessons/research-the-route-before-you-say-cant.md): before "I can't" or
  "you do it", research the route (docs, the machines and sessions already signed in, the tools), then try it or file
  it; only a concrete blocker with evidence and the smallest step only the person can take reach them (w935; w1287:
  the orchestrator told Ben twice it could not make a Claude Design project while his m5 was signed in; Ben: "I
  already asked for this").
- [Drive only the windows you opened](lessons/research-the-route-before-you-say-cant.md#drive-only-the-windows-you-opened-w1287-2026-10-14): computer-use on a person's
  computer touches only windows you opened and your own tools, never their Claude desktop app or other open apps,
  even the signed-in one (w1287: a worker switched Ben's desktop app to Chat mode looking for Design while his
  thread ran; Safari, in its own window, and Claude Code's DesignSync were the routes).
- [A wait is a harness timer, never a background loop](lessons/a-person-wait-is-declared-not-polled.md#a-wait-on-a-machine-is-a-harness-timer-never-a-background-loop-w1106): what must be checked
  after the turn goes to `wake_me`, `blocked_on`, `set_timer` or `waiting_on_person`, which the portal keeps across
  deploys and restarts. Never a backgrounded `sleep` loop, `nohup`, `&` or Monitor: the process ends at an idle reap, a
  sandbox release or a portal deploy, and the loop with it (w1106: w1070's idle poll died at the first deploy, unseen).

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
