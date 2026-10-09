# Merges: the Evidence section

For a pull request that changes what a player sees, or simulation, save or netcode state, or that
claims to fix a reported bug. Docs, tools and tests of existing behaviour need none of this.

Merge your own pull request once its verification is done and CI is green. Don't leave it open
waiting for the person. Hold one only for exceptional risk or a concrete timing reason, and say in
your report which it is and when it will merge
([merge your own pull request](../lessons/merge-your-own-pr.md)). This list is what "verified"
means, and `pr_evidence.py` checks the part a script can check.

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

Tests: FFEditorTests 6494 run, 6479 passed, 0 failed
Determinism audit: 2354 shared heartbeats, no divergence
Save compatibility: none, no saved state is touched

Not verified: the Bats' slot lag (simulation, follow-up PR)
```

- **One row per claim** the title and TL;DR make. The basis is MEASURED (how) or SOURCED (a link
  or path). A claim that rests on a guess is not a row: verify it, or move it to "Not verified"
  and take it out of the title.
- **Kind `visual`** needs the five lines from "Intended look" to "Review"
  ([visual.md](visual.md)). "Built player: no" fails. So does a "Clips" line that does not say
  where the event is.
- **Kind `ui`** (a screen, panel, tab, HUD element or layout; any changed file under `/UI/` with
  Kind `visual` counts) needs the visual lines plus `Content:` (the save and what fills it),
  `Full content:`, `Style:` (the classic panel compared, and the result), `Shots:` (the
  one-line-per-still notes) and a flicker result on `Clips:` or `Flicker:`. A clip of 1 to 9 fps,
  or "a sequence of the shots", fails ([ui.md](ui.md); w718: #1251 passed every other rule).
  Where a line does not apply (a name tag's colour has no grid), write `n/a:` and why.
  Since w733 also `Overlaps:` and `Alignment:` (from `unity-ui/ui_layout.py check`: 0 new overlaps between always-on HUD blocks; an opened panel over the HUD also needs its `Opened panels:` line, w742,
  max drift 2 px or less) and a `Style:` line with a measured delta E (10 or less) and alpha for
  every touched panel; a difference the requester asked for carries `intended (who): "..."`. The
  verdict names its ff-agents version and fails when a newer one is released.
- **A Deck-facing change** (Steam Input, glyphs, the display settings, Deck UI, or an Evidence section that names the
  Deck) needs a `Real Deck:` line: `verified (who, date; Steam client <build>, SteamOS <version>): <what they saw>`, or
  `not verified on a real Deck: <what stays open>`. A Deck tour on a PC cannot show Steam's layout choice, the Proton
  first-frame resolution, the Steam client or touch ([deck.md](deck.md); w684 -> w768, w767).
- **Kind `simulation`** needs "Tests", "Determinism audit" (with the heartbeat count, per the
  `determinism-audit` skill) and "Save compatibility" (the repo's hard rule).
- **A new or moved system, or code that runs per frame or on one peer only** (a request leg, a
  publisher): the PR names the system's group; per-frame code writes nothing the simulation reads
  (`PerFrameSystemCensusTest` passes, a frame-without-heartbeat test pins a move); and the
  determinism run names its frame rates, with a host held near 20 fps against 60 fps clients
  ([verify at a slow host's frame rate](../lessons/verify-simulation-at-a-slow-hosts-frame-rate.md)).
  A reviewer checks the same three things.
- **A changed shader, shader graph, subgraph, include or material** needs a `## Used by` section
  beside `## Evidence`: the output of the game repo's `python3 scripts/asset_usage.py --changed
  origin/develop --markdown`, with the tool's table whole and a basis on every row (`TARGET:`,
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
- **A fix for a Discord report** has its `Discord: https://discord.com/channels/<guild>/<thread>` line
  (or the original message's `/<guild>/<channel>/<message>` link for a message in a channel) in the
  description before it merges, one per report: FFBox tells the reporter from it and nothing else
  ([a fix PR names its Discord report](../lessons/a-fix-pr-names-its-discord-report.md)).
- **A fix for a player's crash or desync report** has a `Report: <report id>` line per report it
  fixes in the description (or the id among its request's subjects): FFBox shows the report fixed
  only from that ([a fix names its player report](../lessons/a-fix-names-its-player-report.md)).
- **"Not verified"** is always there, even when it says "nothing". It is the honest place for
  what you could not check.
- Nothing in the section may be pending. Finish the review, then merge.

## Check it, then merge

```sh
# The newest installed copy (sort -V: `ls | tail -1` picks 1.20.6 over 1.20.41; w712 posted a stale PASS that way).
PE="$(ls -d ~/.claude/plugins/cache/final-factory-agents/ff-agents/*/ | sort -V | tail -1)skills/evidence-gate/pr_evidence.py"
python3 "$PE" --repo Final-Factory/FinalFactory --pr 913
python3 "$PE" --repo Final-Factory/FinalFactory --pr 913 --comment
# The merge itself, gated on the verdict: `&&`, never `;` or a new line (w793).
python3 "$PE" --repo Final-Factory/FinalFactory --pr 913 --comment && gh pr merge 913 --repo Final-Factory/FinalFactory --merge
# FAIL "older than the released ff-agents": update, then run it again (no restart needed for the script).
claude plugin marketplace update final-factory-agents && claude plugin update ff-agents@final-factory-agents
```

It prints PASS or FAIL with the reasons, and exits 1 on FAIL. Chain the merge to it with `&&`
only: after `;` or on the next line of the same command the merge runs on a FAIL too (w793). `--comment` posts the verdict on the
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
