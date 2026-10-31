# Merges: the Evidence section

For a pull request that changes what a player sees, or simulation, save or netcode state, or that
claims to fix a reported bug. Docs, tools and tests of existing behaviour need none of this.

Merge your own pull request once its verification is done and CI is green (in the game repo: the
required `Test in editmode`, which on a PR runs only the touched tests; the whole suite runs after the merge in the master batch, w1180). Don't leave it open
waiting for the person. Hold one only for exceptional risk or a concrete timing reason, and say in
your report which it is and when it will merge
([merge your own pull request](../lessons/merge-your-own-pr.md)). This list is what "verified"
means, and `pr_evidence.py` checks the part a script can check.

**Read the PR's base and the trunk rule again just before you merge** (w1065, 2026-10-12): a base can change after
you open the PR. When w1137 retired `develop`, GitHub moved every open PR based on it to `master`, and the branch's own
CLAUDE.md still said develop. `gh pr view <n> --json baseRefName`, and the rule from `git show origin/master:CLAUDE.md`,
not from your branch's copy. A base you did not pick is a question to stop on, not a detail.

**Compile the merged tree before you wait on CI** (w1555, 2026-10-20, PR #2068): after `git merge origin/master`, or
`ff-pr push`, which merges it in again at push time, list what the merge brought (`git diff --name-only HEAD^1 HEAD --
'*.cs'`). If any `.cs` changed, compile and run your touched tests on the merged head before you push or wait: an API
your branch calls may have changed under it. There, master's `SimCollisionFilter` replaced Unity Physics'
`CollisionFilter` in `FpCollisionWorld.CastRay`; the branch compiled before the merge, CI went red on `error CS1503`,
and one CI cycle was lost.
It recurred in w1572 (2026-10-21, PR #2089): the merge brought w1440's `TargetingSystem.cs:867` reading
`SimCollisionWorld.UseFixedPoint`, which the branch had removed; the compile check had run before the merge.

**A CI fix that edits an asset runs every test and builder that reads it** (w1470, 2026-10-22, PR #1921): when a
red test makes you change an asset (a prefab child removed, a material renamed, a fixture line added), find what
else names that asset or child, `git grep -n -E '<asset file name>|<child name>' -- Assets/Tests Assets/Editor`,
and run those classes too, not only the ones that failed. There, `StructureMapIconsTest` (w1488) failed on the
Lance prefab's hand-placed `StationDisplay` map plane; removing it passed that class, and on the next CI run the
Lance's own `SingularityLanceConfigTest` threw a NullReferenceException reading `Find("StationDisplay")`, and the
editor builder that makes the prefab still set the plane's scale. One CI cycle was lost.

**A red test your diff cannot reach: read master's batch verdict before you rerun** (w2351, 2026-10-27, PR #2686): a
PR's run tests the branch with master merged in, so a culprit already on master fails it too. Before `gh run rerun`,
`gh run list --workflow master-batch.yml -L 10` and, for a red one, `gh run view <id> --log-failed | grep
MASTER_BATCH_VERDICT`: if it names a pull request your branch holds, wait for (or find) its revert on master, merge
`origin/master` in and push; a rerun of the same tree fails the same way. There, an Entities Graphics patch failed
`BlueprintPasteBefore2334DigestTest` twice with the same hash; batch 40494217033 had named #2682 (w2375, three
`ValidationScenarios` blueprint files), already reverted by #2695, and the rerun cost a 30-minute CI cycle.

**After a removal merges, look for the removed names on master** (w1572, 2026-10-21, PR #2089): a PR that deletes or
renames a type, member, package or asmdef reference is checked against the master it merged in, and so is every PR
that merged minutes before it. Once yours merges, `git fetch origin && git grep -n -E '<removed names>' origin/master
-- '*.cs' '*.asmdef'`, and fix a hit at once in its own PR. There, #2090 (w1627) merged minutes before #2089 with
`DysonShellRecordsTest.cs:365` creating `Unity.Physics.Systems.BuildPhysicsWorld`; both PRs were green alone, and
master's test assembly did not compile until #2091.

## What goes in the pull request

```markdown
## Evidence

Kind: visual, simulation          <!-- visual | ui | simulation | visual, simulation | other -->

| Claim | Basis | Where |
|---|---|---|
| A remote rider is drawn on their seat | MEASURED: stepped frames 118-190 of the built-player clip | proofs/after.mp4 |
| No simulation state changes | MEASURED: two-peer determinism audit, 2354 shared heartbeats, no divergence | proofs/audit.txt |

Intended look (Ben): "the other player appears outside of the ship behind it" must not happen
Built player: yes
Clips: proofs/before.mp4, proofs/after.mp4 (the hand-over is at frames 118-190)
Looked: yes, every frame of 118-190 at 2x crop
Review: watch_video report in proofs/review/; no blind model review (no Gemini key here)
Art language: compared with the Railgun's glow in the same still; no ring, circle, halo or UI-like overlay

Tests: FFEditorTests 6494 run, 6479 passed, 0 failed
Determinism audit: 2354 shared heartbeats, no divergence
Save compatibility: none, no saved state is touched

Not verified: the Bats' slot lag (simulation, follow-up PR)
```

- **One row per claim** the title and TL;DR make. The basis is MEASURED (how) or SOURCED (a link
  or path). A claim that rests on a guess is not a row: verify it, or move it to "Not verified"
  and take it out of the title.
- **Effect art** (a changed shader, material or VFX file; icons, sprites, UI, holograms and fog excepted) also needs
  `Art language:` naming the reference compared and saying it draws no ring, circle, halo or UI-like overlay, or
  quoting the person asking for one (`n/a: <why>` for an indicator asked for; visual.md 5c; w1241, w1332).
- **Hero art** (a model file added, or effect art added or rewritten by 40+ changed lines; third-party packs, icons,
  sprites, UI and scripts excepted; `pr_evidence.py` decides from the file list) needs one `Hero art:` line: `concepts:`
  (the 2-3 concept stills shown, who picked which), `detail:` (compared with the game's best models or effects in one
  still), `differs:` (from the Railgun, Plasma Bolt and the other weapons' and effects', "no reuse" or what it reuses),
  `distinct:` (what makes it distinctive), `cost:` (measured ms or fps in a built player). `Hero art: n/a (<why: a bug
  fix, a re-tint, an icon, a re-export, a third-party import>)` shows in the verdict for the reviewer
  (visual.md 5e; w1470, w1466, w1475, w1497).
- **A pick** (the brief or the evidence says someone picked or chose a design, "option C", "look A", or quotes a relayed
  pick such as "C, the Tiles"; `pr_evidence.py` reads it) needs one `Picked (<who>):` line: `still:` (the file or link
  of the option they picked, never only its letter or label), `shows:` (what is visible in it, in a sentence: where on
  screen, its look, the prefab or toggle state), `words:` (their own words, quoted, found in the brief), `matches:`
  (how those words fit that still), `beside:` (a still of the built result beside the picked still). `Picked: n/a
  (<why>)` when what was chosen is no design (a number, a cut depth). Before building, `pr_evidence.py --pick <brief>`
  checks the same line without `beside:` (w1323, w2580, w2669).
- **A world model** (a model file or a mesh `.asset` under `Assets/Art/{Content,Models,ItemArt}/` added or changed, or
  an item, structure, ship or projectile prefab added under `Assets/Resources/{ConnectorEntities,ItemEntities}/` or
  `Assets/Prefabs/EffectsEntities/Projectiles/`; effects, icons, sprites, UI and third-party packs excepted) needs
  `Scale: <built-player still>: <model> beside <its neighbours> at gameplay zoom; its size matches theirs (or the
  ratio)`; an item's line names a connector and an inserter hand. `Scale: n/a (<why: a re-tint, a material only, size
  unchanged, not drawn in the world>)` shows in the verdict (visual.md 5k; w2204, the Repair Pack).
- **A hide or visibility change** (a game script under `Assets/Scripts` named `…Visibility…`, `…Hide…`, `…Hidden…` or
  `…Cull…`, added or changed; UI, the lobby, probes, audits and tests excepted) needs `Hidden census: <census log,
  clip>: with <the thing> hidden in a built player, 0 renderers, particle systems and VFX still drawn inside its bounds;
  it carries <its children, VFX, shields, engines, lights, trails, outlines, labels, icons, attached items>`.
  `Hidden census: n/a (<why: a revert, selection or input only, who owns the setting, nothing drawn changes>)` shows in
  the verdict (visual.md 5l; w2210, Hide Flying Stations).
- **A defect gone or an effect shown** ("no z-fight", "no flicker", "no longer draws through", "ships spaghettify",
  "pulls in", anywhere in the description but the person's quoted words) needs `Close-ups: <claim>: <1:1 crop.png or
  slowed clip.mp4 and its seconds>; ...`, and an occlusion claim also `Surfaces: <every surface the effect overlaps>`
  with a crop over each (visual.md 5g; w1470, w1567). A transition ("stretches in", "swallowed", "dissolves", "stays
  lit as itself", "spaghettify", "pulled in") needs every frame of it cropped on the object, with its seconds:
  `<claim>: <name>-strip-3.40-6.20s-every1f.png` from `transition_strip.py`; a sheet every 0.2 s, a still or a 0.25x
  clip fails, and so does a second opinion's "disappears" beside it with no strip (visual.md 5h; w1470, w1686).
- **Kind `visual`** needs the five lines from "Intended look" to "Review"
  ([visual.md](visual.md)). "Built player: no" fails. So does a "Clips" line that does not say
  where the event is.
- **Kind `ui`** (a screen, panel, tab, HUD element or layout; any changed file under `/UI/` with
  Kind `visual` counts) needs the visual lines plus `Content:` (the save and what fills it),
  `Full content:`, `Style:` (the classic panel compared, and the result), `Shots:` (the
  one-line-per-still notes) and a flicker result on `Clips:` or `Flicker:`. A clip of 1 to 9 fps,
  or "a sequence of the shots", fails ([ui.md](ui.md); w718: #1251 passed every other rule).
  Where a line does not apply (a name tag's colour has no grid), write `n/a:` and why.
  Since w733 also `Overlaps:` and `Alignment:` (from `unity-ui/ui_layout.py check`: 0 new overlaps between always-on HUD blocks; since w981 also a `Window overlaps:` line, open windows against the HUD and each other, 0 new and 0 kept unless the requester's words allow the pair; an opened panel over the HUD also needs its `Opened panels:` line, w742,
  max drift 2 px or less) and a `Style:` line with a measured delta E (10 or less) and alpha for
  every touched panel; a difference the requester asked for carries `intended (who): "..."`. The
  verdict names its ff-agents version and fails when a newer one is released.
  **Run it in its own call and read its first line before you merge** ([lesson](../lessons/merge-your-own-pr.md#merge-only-after-reading-the-checkers-verdict-w978-2026-10-11); w978: a merge chained after it with `;` ran on a FAIL that said "1.26.27 is released"). Merge only on `PASS` from the released version.
- **A Deck-facing change** (Steam Input, glyphs, the display settings, Deck UI, or an Evidence section that names the
  Deck) needs a `Real Deck:` line: `verified (who, date; Steam client <build>, SteamOS <version>): <what they saw>`, or
  `not verified on a real Deck: <what stays open>`. A Deck tour on a PC cannot show Steam's layout choice, the Proton
  first-frame resolution, the Steam client or touch ([deck.md](deck.md); w684 -> w768, w767).
- **Kind `simulation`** needs "Tests", "Determinism audit" (with the heartbeat count, per the
  `determinism-audit` skill) and "Save compatibility" (the repo's hard rule).
- **Save version bumped -> old-save load test present** ([lesson](../lessons/merge-your-own-pr.md#a-save-version-bump-that-keeps-old-saves-loading-needs-no-person-w1826-2026-10-23);
  Ben, 2026-10-23, w1826). The PR's Save compatibility line names the test that loads a save from
  before the bump and says it ran green. With it, the bump merges without a person (a newer save
  refused by an older build is fine); without it, writing it is the work. Only a change that breaks
  loading existing saves goes to a person.
- **A re-pinned digest or golden test says what its fixtures don't carry** ([lesson](../lessons/look-early-by-breakdown.md#a-digest-is-blind-to-fields-its-fixtures-never-carry-w2124-2026-10-25);
  w2124): the Tests line names each field the digest excludes and the assertion that pins its value, any feature the
  change touches that no fixture sets and the test that now sets it, and the mutant arm that went red.
- **A new system has a test that runs it** ([lesson](../lessons/verify-simulation-at-a-slow-hosts-frame-rate.md#a-new-system-runs-in-a-test-before-the-first-in-game-run-w809-2026-10-09)): the PR's Tests line names
  the test that schedules each new `ISystem`/`SystemBase` in a world with a matching entity, presentation and animation
  systems included (w809: a job's aliasing error only showed when a golden fixture loaded in PlayMode).
- **A new or moved system, or code that runs per frame or on one peer only** (a request leg, a
  publisher): the PR names the system's group; per-frame code writes nothing the simulation reads
  (`PerFrameSystemCensusTest` passes, a frame-without-heartbeat test pins a move); and the
  determinism run names its frame rates, with a host held near 20 fps against 60 fps clients
  ([verify at a slow host's frame rate](../lessons/verify-simulation-at-a-slow-hosts-frame-rate.md)).
  A reviewer checks the same three things.
- **The determinism run names its pair and why** (w1692): two players on whatever machines are free, any OS. A
  cross-OS pair (a Mac host against a Windows or Linux client) only for float or math-library use in the simulation,
  Burst or IL2CPP codegen-sensitive code, platform APIs or file paths, the desync hash or its capture, or a desync
  reported only across OSes; the Evidence row says which applied, or "no cross-OS pair: <why>"
  ([any two free machines](../lessons/verify-simulation-at-a-slow-hosts-frame-rate.md#a-determinism-pair-is-any-two-free-machines-a-cross-os-pair-only-when-the-change-can-differ-by-platform-w1692-2026-10-21)).
- **Each client leg proves it reaches the host before it builds or joins** (w2259): `python scripts/nightly/reach.py
  @<host machine>` run on the client's own machine ends `PICKED <ip>`, and the leg joins that IP; `UNREACHABLE` stops
  the leg at once with the addresses tried. A host address is a machine name (`@m3`, `lab_hosts.json`), never a copied
  LAN IP: w2252's LothDesktop client lost every ping to the m3's 10.0.0.110 and waited out a 150 s join timeout
  ([lesson](../lessons/verify-simulation-at-a-slow-hosts-frame-rate.md#a-client-leg-reaches-the-host-from-its-own-machine-first-w2259-2026-10-26)).
- **A pair leg's scenario survives the bench turn** (w2407): each player launches with `player_slots.py launch
  --bench-wait`; a player log with `[QuitSave] ApplicationQuit: not saving (AutomationProcess)` and no quit of its own
  makes that scenario void (say so to the partner and in the report), and each client is ended once its scenario's
  result is taken, so its reconnect cannot join the next host
  ([lesson](../lessons/verify-simulation-at-a-slow-hosts-frame-rate.md#a-pair-legs-player-dies-to-another-workers-timed-run-and-an-old-client-rejoins-the-next-host-w2407-2026-10-27)).
- **A pair run that needs Steam says so** (w2459, 2026-10-28): a check of lobbies, a Steam host, join or invite passes
  `request_pair` `steam: "<why>"` (FF Factory also reads it from a lobby or a Steam join in `what` or `brief`), so its legs
  go only on computers signed in to Steam, a different account on each leg; a direct-IP pair whose words name a lobby
  passes `steam: "none"`. w2458's client leg went on biscuit, which has no Steam client, and died at its Steam check. When
  too few computers are signed in, the run is Blocked on that and names each computer; it starts by itself once they are.
  A leg that clicks the game's menus (every Steam pair, or one whose `what`/`brief` names a menu or a click; else pass
  `menus: "<what it clicks>"`) goes only where the screen is unlocked: w2460's host leg went on m5, signed in to Steam
  behind a locked screen, where a Mac's menus take no clicks. A running Steam that is not connected (BEAST, w2461: "Logged
  In Elsewhere") counts as signed out.
- **A pair run is sized to its slowest required event** (w2570): the brief or scenario names, from measured rates, the
  heartbeat each required event lands at (a latch flip, a crossing), and the leg after the join runs to the latest plus a
  margin, not just the stated minimum; it dumps the checked state at intervals and on every leg at the end
  ([lesson](../lessons/verify-simulation-at-a-slow-hosts-frame-rate.md#a-pair-run-is-sized-to-its-slowest-required-event-not-the-briefs-minimum-w2570-2026-10-29)).
- **A pair run is filed only on a commit that compiles** (w2125): before `request_pair`, the head the legs run has a
  green `Test in editmode` run, or your own editor's `refresh_unity` at that head logged no `error CS`; a red or
  unfinished CI run is not a go
  ([lesson](../lessons/verify-simulation-at-a-slow-hosts-frame-rate.md#a-pair-run-is-filed-only-on-a-commit-that-compiles-w2125-2026-10-25)).
- **After merging `origin/master` in, look for tests it brought that pin what you changed** (w2095, 2026-10-25): grep
  `Assets/Tests` for each constant or member you changed (`git diff origin/master...HEAD`), and run the selection
  again (`scripts/test_select.py`). A guard test merged meanwhile pins the old value: w2129's
  `W2129UiFixGuardTests.DockedTabPillsAreInset16SideAnd10Top` pinned `StructuredDock.TabInsetTop` at 10 while
  w2095 moved it to 18 at Ben's pick, and `Test in editmode` went red only after `ff-pr push` merged master in. Update
  the guard in your PR, quoting the words that asked for the new value.
- **A changed shader, shader graph, subgraph, include or material** needs a `## Used by` section
  beside `## Evidence`: the output of the game repo's `python3 scripts/asset_usage.py --changed
  origin/master --markdown`, with the tool's table whole and a basis on every row (`TARGET:`,
  `MEASURED:` naming a built-player before/after, or `SOURCED:`). The game repo's CI job
  `asset-usage.yml` checks the same list against the PR's own diff
  ([check who uses a shared asset](../lessons/check-who-uses-a-shared-asset.md)).

  ```markdown
  ## Used by

  asset-usage: `Assets/Art/Shaders/AltIconSprite.ShaderGraph` has 1 user (1 material); they are used by 1 prefab

  | User | Basis |
  |---|---|
  | `Assets/Art/Materials/AsteroWorldSpriteMat.mat` | TARGET: the Alt-view icon template (Evidence above) |
  ```
- **Content or a feature not ready for players** (new items, recipes, buildings, research, belt models) is gated by
  a feature toggle that is off for players, and the description names it and how to turn it on (`-ffFeatures=<id>`,
  Final Factory > Feature Toggles); a Simulation toggle's row names its two-peer run with it on
  ([unfinished content goes behind a toggle](../../project-memory/memories/feedback-unfinished-content-behind-a-toggle.md)).
- **A fix for a Discord report** has its `Discord: https://discord.com/channels/<guild>/<thread>` line
  (or the original message's `/<guild>/<channel>/<message>` link for a message in a channel) in the
  description before it merges, one per report: FFBox tells the reporter from it and nothing else
  ([a fix PR names its reports](../lessons/a-fix-pr-names-its-reports.md#its-discord-report)).
- **A fix for a player's crash or desync report** has a `Report: <report id>` line per report it
  fixes in the description (or the id among its request's subjects): FFBox shows the report fixed
  only from that ([a fix PR names its reports](../lessons/a-fix-pr-names-its-reports.md#its-player-report)).
- **An FFBox branch is reviewed file by file against its report**: its run can end with a commit
  `ffbox <run>: uncommitted work at exit` that sweeps in editor serialization noise. In w944, #1422's fix for a stop
  drag also carried `DysonBeam.mat` `m_CustomRenderQueue` 3000 -> 2000, a render change nobody asked for. Run
  `git diff origin/master...<branch> --stat`, and put back every file the report does not explain before you land it.
- **Before the merge's first git write after a wait**, `git branch --show-current` names your branch
  (`lessons/merge-your-own-pr.md`, w807). **Post the verdict with `--comment` only from the
  newest ff-agents**: a stale copy's FAIL is about the copy, so `pr_evidence.py` now refuses to post it.
- **"Not verified"** is always there, even when it says "nothing". It is the honest place for
  what you could not check.
- Nothing in the section may be pending. Finish the review, then merge.

## Check it, then merge

```sh
# The newest installed copy (sort -V: `ls | tail -1` picks 1.20.6 over 1.20.41; w712 posted a stale PASS that way).
PE="$(ls -d ~/.claude/plugins/cache/final-factory-agents/ff-agents/*/ | sort -V | tail -1)skills/evidence-gate/pr_evidence.py"
python3 "$PE" --repo Final-Factory/FinalFactory --pr 913
python3 "$PE" --repo Final-Factory/FinalFactory --pr 913 --comment
# The merge itself, gated on the verdict: `&&`, never `;`, a new line (w793) or a pipe before it (w888).
python3 "$PE" --repo Final-Factory/FinalFactory --pr 913 --comment && gh pr merge 913 --repo Final-Factory/FinalFactory --merge
# FAIL "older than the released ff-agents": update, then run it again (no restart needed for the script).
claude plugin marketplace update final-factory-agents && claude plugin update ff-agents@final-factory-agents
```

It prints PASS or FAIL with the reasons, and exits 1 on FAIL. Chain the merge to it with `&&`
only: after `;` or on the next line of the same command the merge runs on a FAIL too (w793). Never pipe the
check's output before the `&&` (`| head`, `| tail`, `| grep`): a pipeline's exit status is its last command's, so
`pr_evidence.py ... 2>&1 | head -2 && gh pr merge` merges on a FAIL (w888, #1393). To trim the output, redirect it to
a file and test the exit (`pr_evidence.py ... > v.txt 2>&1 && gh pr merge ...`). `ff-pr merge` reads CI, not the
verdict: gate it the same way (w1684, #2148: `... --comment 2>&1 | head -2; ...; ff-pr merge` merged on a FAIL; w2083, #2484: `pr_evidence.py ... 2>&1 | tail -3 && gh pr edit ... && ff-pr merge` merged on a stale-copy FAIL). A
draft checked with `--body-file` needs the PR's files too (`--repo`, `--pr`; before 1.29.82 it ran with none, so the
Balance and Used by rules never fired on the draft). `--comment` posts the verdict on the
pull request, so there is a record, timestamped before the merge, of what the evidence was. Run it
again after you change the description. A FAIL means fix the evidence or the claim, not the
wording.

`--audit --since 2026-10-01` lists merged pull requests with their verdict and whether a PASS
comment existed before the merge. A reviewer, or an orchestrator's worker, can run it over the
changes going into a release.

What the script cannot do: judge whether you looked carefully. It checks that the claim, the
basis and the place to look are written down, that nothing is pending, and that a visual change
names a built player, the event's frames and the intended look.

## After the merge: close the request

When the PR serves an FF Factory request (its `Request: wNNN` line) and every step after the merge
is finished too, end your report with a line `DONE: wNNN` and say there how each step after the
merge went; while one is left, say which instead. The ledger closes the request on that line
([say DONE per request](../lessons/say-done-per-request.md)).

Lessons behind this list:
[merge your own pull request](../lessons/merge-your-own-pr.md),
[no merge before the review](../lessons/no-merge-before-the-review.md),
[a visual fix is verified by looking](../lessons/visual-fixes-are-verified-by-looking.md).
