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

Kind: visual, simulation          <!-- visual | simulation | visual, simulation | other -->

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
- **"Not verified"** is always there, even when it says "nothing". It is the honest place for
  what you could not check.
- Nothing in the section may be pending. Finish the review, then merge.

## Check it, then merge

```sh
python "<this skill's base directory>/pr_evidence.py" --repo Final-Factory/FinalFactory --pr 913
python "<this skill's base directory>/pr_evidence.py" --repo Final-Factory/FinalFactory --pr 913 --comment
```

It prints PASS or FAIL with the reasons, and exits 1 on FAIL. `--comment` posts the verdict on the
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
