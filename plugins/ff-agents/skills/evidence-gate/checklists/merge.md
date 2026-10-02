# Merges: the Evidence section

For a pull request that changes what a player sees, or simulation, save or netcode state, or that
claims to fix a reported bug. Docs, tools and tests of existing behaviour need none of this.

You are trusted to merge verified work on your own. This list is what "verified" means, and
`pr_evidence.py` checks the part a script can check.

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

Lessons behind this list:
[no merge before the review](../lessons/no-merge-before-the-review.md),
[a visual fix is verified by looking](../lessons/visual-fixes-are-verified-by-looking.md).
