---
name: measure-moving-presentation-on-moving-things-and-check-the-clips
description: "A fix to how something MOVING is drawn is measured on moving, free-flowing things (a backed-up belt parks its items, and parked entities are drawn at their simulation position, so the fix shows nothing there), and every before and after clip is checked for its size and for the game being what was recorded before any number is taken from it."
date: 2026-10-12
---

# Measure moving presentation on moving things, and check the clips first

**Rule.** (1) A change to how a moving thing is drawn (belt items round a corner, a ship's turn, an interpolated pose) is
filmed and measured while the things MOVE. A queue that has backed up is parked: the interpolation render skips
parked entities and draws them at their simulation position (w950), so a before and after of a full belt are the same
picture. Film the first seconds after the line is built, or give it a sink that really takes the flow (an unpowered
Cargo Hold refuses items). (2) Before you measure a clip, look at its first still (is it the game, not another window
on top: a recorder grabs a screen region) and read its size with `ffprobe` (the old nightly player re-applies a stored
window size and ignores `-screen-width` on some launches, so "1280x800" before and "1920x1080" after are not
comparable). (3) Measure against what the player sees: the tubes of the drawn belt, fitted from the frame, never the
code's own path.

**Why.** w1086 (lothsahn, 2026-10-12: "Tell the w1086 worker to do it rendered and not guess"): items on belt corners
were drawn on a quarter circle 2.07 u inside the tile's middle, where the L-shaped curve piece's tubes meet. The first
clips were of belts backed up behind an unpowered Cargo Hold: items parked, nothing differed between builds. The
recorder then hung twice (`ddagrab`, an empty raw file for 20 minutes), one run recorded WinDirStat because
`run_fleet_motion.raise_window` passed HWND_TOPMOST as a 32-bit int (`SetWindowPos` did nothing on 64-bit Windows), and
before clips came out at two sizes. A temp-folder wipe while the sandbox was stopped lost the first set of clips and a
build: publish the proofs (`publish_review`) as soon as they exist.

**How to apply.** `scripts/feel/run_w1086_belt_corners.py` (free-flow capture, `--no-sink --no-layout --hold 0.5`) and
`analyze_w1086_corners.py` (whole-item centre against the fitted tubes, in tiles) in the game repo are the pattern.
`ffauto:pointer.moveto|x|z` answers a tile's screen position through the game's own camera (bottom-left origin, on the
ground plane, so raised things sit a constant offset from it). Kill your own player by pid
(`python -c "subprocess.run(['taskkill','/PID',...])"`): killing by image name is blocked by a hook.
