<!-- w1567: the claim lines of PR #1921 (Final-Factory/FinalFactory, w1470 Singularity Lance) as of 2026-10-19, verbatim; the rest of its description is left out. Ben then saw both claims wrong. -->

## Evidence

Kind: visual, simulation

| Claim | Basis |
|---|---|
| It kills the Guardian in one shot | MEASURED: built player 943bd457c2, the boss clip below: the Lance picked the Guardian itself, and the Guardian spaghettified and died |
| No z-fight with the Antimatter Nexus | MEASURED: the nexus clip: the ring occludes the hole with a stable edge; frame-to-frame flicker over 59 frames had a median of 2.1/255 and a max of 9.6/255 |

Intended look (Ben, 2026-10-18): "ships that get sucked in should die not just get stuck in the middle then
explode after, make them spaghettify (with a performant shader) ... if the black hole dissipates before they 'finish'
the spaghettification animation they should just smoothly explode with the effect's explosion effect, and also add some
more particles to the explosion effect / ... make the black hole itself look like its spinning more ... it can even kill
the boss in one shot." The standing brief: "two solid colours plus one bright, bloomy HDR accent; the VFX sits in the
game world and never looks like a UI ring or indicator".

Built player: yes, a Mac player of 943bd457c2, launched through `scripts/nightly/player_slots.py`.

Clips: before, the ability version Ben turned into a structure (`/srv/fff/review/w1470-singularity-lance-v2/`, `lance-20261018-190849.mp4`); after, the structure's four takes below (`/srv/fff/review/w1470-singularity-lance-structure/`):
- `w1470-lance-boss-60fps.mp4` (7.0 s, 48.2 distinct fps): the Lance picks the Ancient Guardian itself; the well opens on it, it spaghettifies and is gone.
- `w1470-lance-camp-60fps.mp4` (7.0 s, 46.5 distinct fps): a cluster by the Antimatter Nexus; ships spaghettify into the core, the rest fade out in bursts at the collapse.
- `w1470-lance-disc-60fps.mp4` (6.0 s, 45.7 distinct fps): the spinning disc close up, then the collapse's particles.
- `w1470-lance-nexus-60fps.mp4` (6.1 s, 47.1 distinct fps): the well beside the Nexus ring, which passes in front of it with a stable edge.
- `w1470-lance-boss-earlier-take.mp4`, the `*-sheet.png` contact sheets and the `*-closeup.png` crops.

All four are 1920x1136, recorded 2026-10-19 00:40. Distinct fps was measured with ffmpeg mpdecimate; the 23:31 takes measured about 33 under machine load.

Looked: yes. I stepped through each clip and its close-ups: the spaghettify (the hulls stretch into the core and thin
out), the early-fade bursts at the collapse, the spin, the Guardian kill and the Nexus edge. watch_video's second opinion has not been run yet.


Not verified: the two-peer run (it needs a Windows lab); the balance stage (it needs lothdesktop); a Windows capture; not verified on a real Deck; Ben's approval of the concepts, the model and the clips.
