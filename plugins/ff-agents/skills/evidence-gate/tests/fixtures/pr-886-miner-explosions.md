<!--
Fixture for test_pr_evidence.py and replay-2026-10-02.md.

FinalFactory #886, "Death explosions: sized from the unit's own body; timed-out orphan bots do not
explode", merged 2026-10-01 23:27 UTC, 39 minutes after it opened. The pull request had no Evidence
section. This is the section it could honestly have written, taken from its own description; "not
stated" stands where the description is silent.
-->

## Evidence

Kind: visual

| Claim | Basis | Where |
|---|---|---|
| A miner bot's explosion is sized from its own body (radius 8, fireball 9.1) | MEASURED: 60 fps frame sequences from the editor rig, miner bot, Bat and Razor at one zoom | specs/w171-miner-bot-explosion-scale/proofs/after_trio.mp4 |
| A timed-out orphan bot shows no explosion | MEASURED: the rig set the orphan timer by hand, then the real death path ran | specs/w171-miner-bot-explosion-scale/proofs/after_orphan.mp4 |
| No simulation, save or network state changes | SOURCED: Assets/Scripts/FFSystems/Presentation/DeathExplosionVfxSystem.cs is the only system changed | the diff |

Intended look: not stated
Built player: no. Frame sequences from the rig in the editor; no real station was deconstructed. Stills of a Ship Yard on two built peers.
Clips: before_trio.mp4, after_trio.mp4, before_orphan.mp4, after_orphan.mp4
Looked: not stated
Review: watch_video --mode vfx on the rig clips (review-trio, review-orphan)

Not verified: the orphaned-bot case on two peers; a real deconstruct in a built game
