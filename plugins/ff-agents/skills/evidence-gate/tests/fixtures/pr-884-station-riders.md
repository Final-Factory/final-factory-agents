<!--
Fixture for test_pr_evidence.py and replay-2026-10-02.md.

FinalFactory #884, "Two players on one mobile station: riders, Bats and beams drawn on the ship",
merged 2026-10-02 01:58 UTC. The pull request had no Evidence section. This is the section it could
honestly have written, taken from its own description; "not stated" stands where the description is
silent.
-->

## Evidence

Kind: visual

| Claim | Basis | Where |
|---|---|---|
| The other player's ship is drawn on its seat | MEASURED: distance from the seat on both screens, mean and max 0.0 u in four runs on two built players | specs/mp-station-riders/proofs/numbers/after-client-200.txt |
| Parked Bats stay on their platforms | MEASURED: mean 0.8-1.3 u, max 5.6-11.7 u from their place | specs/mp-station-riders/proofs/numbers/after-host-0.txt |
| No simulation, saved or networked state changes | MEASURED: two-rider determinism audit, 2354 shared heartbeats, no divergence | specs/mp-station-riders/proofs/numbers/two-rider-audit-compare.txt |

Intended look (Ben): "the other player appears outside of the ship behind it. if you have bats and defense platforms on the ship, they lag" must not happen
Built player: yes
Clips: specs/mp-station-riders/proofs/client-drives-200ms/fly-hand-over-before-over-after.mp4 and eleven more, one per leg, before over after
Looked: not stated
Review: watch_video --mode vfx reports beside two close-ups; no blind model review (no Gemini key on LothDesktop)

Not verified: the Bats' slot lag in the simulation (a follow-up pull request)
