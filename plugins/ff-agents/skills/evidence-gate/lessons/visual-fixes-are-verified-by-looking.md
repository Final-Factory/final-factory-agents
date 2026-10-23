---
name: visual-fixes-are-verified-by-looking
description: "A visual or feel fix is done only when someone looked at it, and the person looks at it inline: each still and clip as ![name](<absolute path>), never a bare path or folder (w1384) (new art also matches the art language, checked against a reference asset): a built player, a clip that contains the event, compared with the intended look in the person's own words. Measurements and watch_video support the look; they do not replace it."
date: 2026-10-11
---

# A visual fix is verified by looking

**Rule.** A change a player sees is verified in a built player, with before and after clips that
contain the event, checked frame by frame against the intended look as the person described it.
`watch_video` and its blind model review are a second opinion. A measurement, a pull request
title or a tool verdict is not a look.

**Why.** Three fixes merged on 2026-10-01 and 02 on evidence for a different claim.

- **Two players on one mobile station (#884).** Verified by position numbers: the other rider's
  ship was 0.0 units from its seat. In the 0.50.0.64 build Ben found the rider still drawn with
  engine exhaust. The numbers measured where the ship was, not how it looked.
- **Miner bot death explosions (#886).** The proof was frame sequences from an editor rig; the
  pull request says "No real station was deconstructed". It merged 39 minutes after it opened. In
  the same build Ben found the explosion still huge.
- **Quick craft asking for an item a bot is carrying (#913).** Merged 37 minutes after it opened
  with "The `watch_video` review is pending". Its clips were editor frames at about 12 fps, and
  by the orchestrator's account they did not contain the moment the report was about.

The orchestrator had reported the first two to Ben as fixed. Ben: "did you even visually verify
this", "VISUALLY VERIFY STUFF WITH VIDEO". Its record of that week also says the blind model
review passed clips that did not contain the event, and approved a mistake because the brief
described the mistake as the intended look.

**How to apply.** [The visual checklist](../checklists/visual.md), in short:

- Quote the person's description of what is wrong or what they want. Don't review against your
  own description alone.
- A built player from the slot pool, and the real event reached the way a player reaches it.
- Name the frames where the event is. Step through them yourself, at a zoom where the detail
  shows.
- Report what you looked at. "Fixed" is for what was seen; otherwise say "changed, not yet seen
  in a built game".
- An orchestrator does not report a visual fix as done from a title, a table or a verdict. It
  says what evidence the worker named.

## Hunt for what should not be there (w895, w1015)

**Rule.** A visual check has two questions, asked separately: (1) is each thing the brief asked for
there, and (2) what is on screen that the brief did not ask for? Answer (2) for every still and every
frame of every sheet, as a written list: duplicate or leftover objects, ghost copies, dark or unlit
silhouettes, stale UI, things overlapping or drawn on the wrong layer, flicker, clipped text. Each
item is explained (and the person would call it intended) or fixed before the word "matches".

**Why.** Ben corrected the same miss twice.

- **w895, PR #1406 v2 (2026-10-10).** The worker verified a hover card by a measurement (census
  depth) instead of looking at the still. The card still read on top of the Defense Platform panel.
  Ben: "the hover panel is clearly showing over the defense platform and then also intersecting with,
  like, those sliders and stuff, which is bad, but it should just be behind the panels altogether."
- **w1015, victory cinematic, PR #1487 (2026-10-11).** The worker checked sixteen labelled frames and
  said they "match" Ben's six steps. The clip shows a dark ghost copy of the vessel left behind during
  the pan. Ben: "why is there a black ghost vessel that stays behind, it looks weird".

In both, the evidence was read against the request ("is X there?"), so anything extra was invisible
to the check: nobody was looking for it.

**How to apply.**

1. After the "matches the brief" pass, do a second pass with the brief closed. Per frame write one
   line: what is visible that was not asked for, or "looked for ghosts, leftovers, silhouettes,
   stale UI, overlaps, z-order, flicker, clipped text: none".
2. Zoom on the moving thing's start position, the area behind a camera pan, and every edge where two
   panels or objects meet. Ghosts live where the object was a moment ago.
3. `watch_video --mode vfx` has an "Out of place" section answered without the brief. It is a second
   opinion: read it, then look yourself; its silence clears nothing.
4. Put the list in the report under "Looked for, not asked for". The checklist line is
   [visual.md](../checklists/visual.md) item 5b (Artifact hunt).

## Every "it's gone" is shown close up, against every surface (w1567)

**Rule.** A sentence that says a visual defect is gone ("no z-fight") or that an effect happens ("ships spaghettify",
"pulls in the boss") is a claim with its own proof: a full-resolution (1:1) crop of that exact moment, or a slowed clip
segment of it (0.25x and its seconds). A z-fight or occlusion claim is shown over every surface the effect overlaps
(terrain, structures and hulls, other effects), not one. The fresh critic gets each claim as a question to answer from
those crops, not as a statement to agree with.

**Why.** Ben corrected the same claim twice on w1470, the Singularity Lance's black hole (PR #1921):

- **2026-10-18, v2 clips.** The worker's review and a video review passed them. Ben: "visually it looks like its z
  fighting in the screenshot with the antimatter nexus or something, and its not pulling in the boss".
- **2026-10-19, the A/B/C previews.** The fix depth-tested the hole once at its own front. Its proof (PR #1921 Evidence)
  was one clip, `w1470-lance-nexus-60fps.mp4`, against one occluder: "the ring occludes the hole with a stable edge;
  frame-to-frame flicker over 59 frames had a median of 2.1/255". The spaghettify rested on the worker's own look
  ("the hulls stretch into the core and thin out") with "watch_video's second opinion has not been run yet". The note
  said the z-fight was gone and that ships spaghettify into the core. Ben: "the units dont really spagettify when they
  get pulled in and also theres still weird z fighting where the blakc hole isnt overtop of the terrain".

A z-fight at the hole's edge covers a few pixels; a frame-wide median hides it, and the terrain was never in a check.
A stretch on a ship that is a few dozen pixels long in a 1920x1136 camp shot does not show on a contact sheet. The
close-up crops that existed (`*-closeup.png`) were not tied to a claim, and nobody but the author was asked about one.
(Read from PR #1921's description and its `specs/w1470-singularity-lance/plan.md`; the worker's transcript and the
portal's review folder were not reachable from the w1567 sandbox, so the scale it judged at is inferred, not read.)

**How to apply.**

1. While writing the note, mark each defect-gone or effect-present sentence. For each, cut a 1:1 crop of the moment
   (or a 0.25x segment), name it after the claim, and write `Close-ups: <claim>: <file>; ...`.
2. For an occlusion claim, write `Surfaces:` with every surface the effect's footprint crosses in any shot (look at the
   terrain under it, the buildings beside it, the other VFX in front), and crop the edge over each.
3. Run `pr_evidence.py --note <note.md> --questions q.md` before `publish_review`: it fails a claim without a close-up
   or a surface without its crop, checks the files are in the note's folder, and writes the claims as questions.
4. Hand the fresh critic `q.md` and the crops (a new subagent, or `watch_video --mode vfx --brief q.md`). Its answers
   go in the note; a "no" or "can't tell" sends the claim back. The checklist line is [visual.md](../checklists/visual.md)
   item 5g; the PR's Evidence carries the same `Close-ups:` and `Surfaces:` lines, which `pr_evidence.py` checks.

## A transition is stepped every frame on the object, and "it disappears" is cleared only that way (w1686)

**Rule.** A claim that an object turns into its end state ("stretches into the core", "is swallowed", "dissolves",
"stays lit as itself", "one smooth animation") is shown by **every frame** of the whole transition (every 2nd at 50 fps
or more), cropped on the object, from the frame before it starts to its stated end state, on one numbered sheet beside
the claim. In each frame the object's own model is on screen, a little thinner or smaller than in the one before, until
that end state; a frame where it is gone or swapped for something else before then is a pop, and the claim is false. A
sheet every 0.2 or 0.5 s, a still, or a clip played at 0.25x is not that proof. When a second opinion says the object
"disappears" or "snaps", only that strip, asked of a fresh critic, clears it: never the author's reading of a coarser
sheet.

**Why.** w1470, the Singularity Lance (PR #1921), the Guardian vanishing mid-swallow. Ben corrected the look of the
same swallow four times: 2026-10-18, "its not pulling in the boss"; 2026-10-19, "the units dont really spagettify when
they get pulled in"; 2026-10-19, "right now shit just kind of explodes upon reaching the black hole"; and 2026-10-21,
after the round-4 clips and a swallow preview: "The problem is the guardian especially doesn't really smoothly transition
to the spaghetti state it just kind of disappears. I want one smoth animation for the model getting stretched and sucked
into the black hole." The w1567 close-up rule above (filed 2026-10-19, after the second correction) was on, and missed it
three ways (read from PR #1921's round-4 Evidence; `tests/fixtures/pr-1921-round4-swallow.md` holds those lines):

- **No claim was seen.** Round 4 wrote "the Guardian stretches in about 4.0-5.6 s", "a slower swallow" and "seen as
  itself as it stretches". None matched the w1567 words (`stretch` needed "into" or "out"), so `pr_evidence.py` asked
  for no close-up; the ones listed were voluntary, and a round-3 clip stood in for round 4's stretch.
- **The proof stepped too coarsely.** The swallow's close-up was `w1470-r4-B-guardian-swallow-every-0.2s-3.4-6.2s.png`:
  1 frame in 12 at 60 fps. The 2026-10-21 preview, by the orchestrator's account, was stepped every 0.5 s (1 in 30) and
  reported that ships "stretch" and "stay lit as themselves". A model that goes in about 0.1 s (6 frames) falls between
  two samples, and each sample alone looks right. (The preview's note sits in the portal's review folder, which this
  sandbox cannot read.)
- **The critic saw it and was overruled.** watch_video's second opinion on the Guardian take said "the Guardian
  disappears at once". The author cleared it as "its glowing hull going to the ghost's lit hull at capture (it then
  stretches in over about 1.6 s)", citing the 0.2 s sheet. The swap at capture is the very frame Ben saw.

**How to apply.**

1. Mark each transition sentence in the note. Find the frame before it starts and its stated end state (gone, in the
   core) in the clip, and crop on the object (the w1567 close-up): `python3 transition_strip.py <clip> --from <s> --to
   <s> --crop W:H:X:Y --claim <name> --object "<the Guardian>" --out <note folder>`. It writes
   `<name>-strip-<from>-<to>s-every1f.png`, every frame numbered, frames whose change from the one before is over 4x the
   window's median framed in red ("POP?"), and prints the `Close-ups:` entry and the critic's question.
2. Look at every frame yourself: the model present, thinning a little each frame, until the end state. A red-framed
   frame is where to look first, not a verdict (a crackle strike spikes too); an unmarked sheet clears nothing.
3. Put the entry on the `Close-ups:` line and hand the sheet and the question to a fresh critic: "is the model on
   screen in every frame until its end state; name the first frame where it is gone or replaced". A "no" sends the
   transition back to the code, not to a rewording.
4. A second opinion that says "disappears", "vanishes", "at once" or SNAP during a claimed transition is answered with
   that strip of the flagged moment, never with an explanation. `pr_evidence.py` (and `--note`) fails a transition claim
   without an every-frame entry with its seconds, names a coarser sheet, and fails a vanish flag beside a transition
   claim with no strip. The checklist line is [visual.md](../checklists/visual.md) item 5h.
5. On the model staying on screen alone the claim is not proven: the same strip, run with `--track X,Y`, also frames a
   one-frame jump in the object's place (orange, JUMP) and a turn to colours that are not its own (magenta, HUE), and
   the critic is asked both (w1685, Ben, after a clip passed "no vanish, pop, swap or jump": "it suddenly jumps to the
   center of the black hole and then also becomes that purple"; [section](#a-transition-keeps-its-place-and-its-colours-w1816),
   checklist 5i, 5j).

## A transition keeps its place and its colours (w1816)

**Rule.** A transition clip (a swallow, a stretch, a pull, a dissolve) is checked for three faults, each frame by
frame on the object, before a person sees it:

1. **A pop**: the object's own model gone or replaced in one frame (w1686, checklist 5h).
2. **A jump**: the object moving further in one frame than its speed in the frames around it, or creeping and then
   lunging (several times its pace in a few frames), e.g. into the hole's centre.
3. **A colour swap**: the object turning colours that were not its own in its first frames (here purple), instead of
   keeping its hull's colours (a heat glow on them is a choice the person named, not a swap).

`transition_strip.py` measures all three and frames them on the sheet (POP red, JUMP and LUNGE orange, HUE magenta; a
green dot is where it tracked the object). The fresh critic gets all three as questions. A clip that a worker, a critic or the
tool passed while one of these is in it goes back, whatever the note says.

**Why.** Two corrections from Ben of the same kind, both on the black-hole swallow:

- w1470, the Singularity Lance, 2026-10-21. The worker's note said ships "stretch" and "stay lit as themselves". Ben:
  "The problem is the guardian especially doesn't really smoothly transition to the spaghetti state it just kind of
  disappears. I want one smoth animation for the model getting stretched and sucked into the black hole."
- w1685, the same swallow on the map's black holes, 2026-10-22. The worker, a fresh critic and `transition_strip.py`
  (final-factory-agents PR #322) all passed the clip: "no vanish, pop, swap or jump". Ben: "i dont like that it
  suddenly jumps to the center of the black hole and then also becomes that purple. it'd be cool if it more smoothly
  swirled into the black hole and used the objects actual colors with perhaps some heat glow effect"

The tool looked only at how much the crop's pixels changed from one frame to the next, so a ship that moves without
vanishing never stood out against the hole's own swirling disk, and a hull that turns purple over a few frames changes
almost nothing per frame. The critic was asked only "is its own model on screen in every frame", and answered that
question, not the two Ben asked.

What the two w1685 clips show, measured with the defaults below (w1816, 2026-10-22; the half-speed take is
`w1685-final-half.mp4`, the normal one `w1685-final-normal.mp4`):

- **Purple.** The ships' first frames are a navy hull, cyan lights and the disk's orange showing at their edges. From
  f114 (1.90 s) to f246 the tracked ship is 97% at most in purple and magenta (median hue 255-275 degrees) at normal
  speed, and from f144 to f235 at half speed: both marked HUE.
- **The jump.** No frame teleports the ship. It creeps along the rim at about 1 px a frame for some 1.5 s, then its
  strand's tail shoots down into the hole while its head stays at the rim, so the object's centre moves into the
  hole several times faster than before: normal speed f211 (3.52 s), 24 px in one frame against 1.7 around it, and
  2.3 px a frame over 6 frames after 0.6 before (JUMP and LUNGE); half speed f276 (4.60 s), 3.6 px a frame after
  1.1 (LUNGE). Both are about 2 s of game time after the ships reach the rim. That is the "suddenly jumps to the
  center ... it'd be cool if it more smoothly swirled" Ben saw: a lunge, not a teleport, which is why the check
  looks for both.
- **Controls.** The same clips before the swallow (normal 1.62-1.82 s, half 1.00-1.48 s) mark nothing; the ships
  creeping along the rim (normal 1.62-2.95 s) mark no jump or lunge. A smooth synthetic spiral marks nothing
  (`TransitionJumpAndPaletteTest`). Before this change the half-speed take also showed 14 false pops: it shows every
  frame twice, so half its steps were 0 and every real step looked 4x the median.

**How to apply.**

- Run the strip on one object, with a point on it in the first frame it is in:
  `uv run transition_strip.py <clip> --from <s> --to <s> --crop W:H:X:Y --track X,Y --claim <name> --object "<name>"`.
  A box `--track X,Y,W,H` follows everything in it (a group of ships) and suits the colour check; for the motion
  checks track one ship, since a group's centre moves when one of its ships fades. Check the green dot stays on the
  object in every frame; a move marked "its size changed over 1.8x too" may be the tracker taking a neighbour (ships
  merging or parting): look at that frame and the one before before you call it either way.
- **What is the object** (`--diff 80`): a pixel that differs by over 80/255 from the median of the frames 8-30 away
  on each side (half a second of clip is read beyond each end for that). Measured on w1685: the disk's own change is
  50-79 at the 99th percentile, the ship's 210-230; at 40 the ship merged with the disk.
- **JUMP** (`--jump 4 --jump-min 0.5`): its centre moves over 4 times its median move of the 6 frames each side in one
  frame, and over half its own size. 4x matches the pop check; a size floor, not a share of the crop, so the crop you
  choose does not decide it (a 4% floor missed w1685's drop in a 480 px crop and caught it in a 220 px one).
- **LUNGE** (`--surge 3`): over 6 frames it moves over 3 times faster than its median pace over the 30 frames before,
  and over half its size: the creep-then-drop above, which takes several frames and so is not a one-frame jump.
- **HUE** (`--hue 0.35`): its palette is every colour class (neutral, or a 10-degree hue bin) with 4% or more of its
  pixels in its first 3 frames, widened a bin each side. A frame with 35% or more of the object outside it is marked;
  one where the object is under 15% of its first size is left to the eye (a speck in the hole is mostly the hole). A
  glow the person asked for is not foreign: `--allow-hues heat` (white, red, orange, yellow) for Ben's "perhaps some
  heat glow effect", or name the hues.
- A half-speed take that shows each frame twice is found by itself (35% or more of its frames copies) and its copies
  leave the pop, jump and lunge medians.
- The marks point the eye; they do not judge. Look at every marked frame and the one before it, and ask the fresh
  critic the printed question, which asks all three: is it on screen every frame, does it move about as far each
  frame as in the frames around it (or creep and then lunge), does it keep its first-frame colours.
- Run a control from the same clip before the effect starts: it marks nothing with the same thresholds, or the
  thresholds or the track are wrong, not the effect.

## New art matches Final Factory's art language (w1066, w1241, w1332)

**Rule.** Before a preview of new art (a model, a material, a glow, a highlight) goes to Ben:

1. **Two solid main colours and one bright, bloomy HDR accent.** That is how the existing
   powered buildings and ships are built. A new model or material gets the same three parts: no
   extra palette, no flat all-over tint, no missing accent.
2. **A highlight is the object's own material.** To mark something in the world (a powered
   building, a stronger enemy, a selected thing) drive its emissive/HDR accent so it blooms, or add
   rim light, the way the existing buildings and ships are lit. Do not add a world-space sprite,
   halo, ring, aura or any UI-like indicator drawn around it, unless the brief asks for an
   indicator.
3. **Side by side with a reference, in one still.** Put the new asset next to an existing one that
   is built the right way (the Railgun, other powered buildings, existing enemy ships), same camera,
   same lighting, bloom on. Look at it yourself: do the main colours, the accent and the glow read
   as the same family?
4. **The PR's evidence names the reference asset compared and shows that still.**

**Why.** Ben corrected the same kind of miss twice on 2026-10-13.

- **w1066, assembler makeover, PR #1683.** The new assemblers had no bright accent. Ben: "final
  factory art is characterized by basically two solid main colors, then an HRD color that is
  bright and bloomy. look at any other powered building, including the railgun which you made. you
  didnt add this to the assemblers here".
- **w1241, super enemies, PR #1678.** The super's look was a gold halo around the ship. Ben: "i
  dont like that the glow effect is more like a world space UI indicator, isntead of making the
  ship itself glow more naturally".

Both passed the worker's own check, because that check asked "is the requested look there?" and
never "does it look like the rest of the game?". Neither worker held the new asset up against an
existing one.

- **w1332, comet catch tail, PR #1816 (2026-10-15).** The first pass held the comet's head in two turning
  "containment rings" and ended the landing with a ring running out. Rule 2 above was already written; the worker read
  it only as a review step, after the effect was built and the clips sent. Ben: "again I don't like the unnatural
  circle effect that looks like UI. The vfx should be part of the game world in its appearance. The actual vfx is cool
  tho". The fix kept the tail and the fizzle and dropped both rings; the impact later got its punch from a flash of
  light and debris streaks, not a ring. That was Ben's second correction of this kind, so it is now a tool check:
  `pr_evidence.py` fails a visual PR that changes effect art (a shader, material or VFX file; icons, sprites, UI,
  holograms and fog excepted) without an `Art language:` line naming the reference it was compared with and saying it
  draws no ring, circle, halo or UI-like overlay, or quoting the person asking for one (fixture
  `tests/fixtures/pr-1816-comet-catch-tail.md`).

**How to apply.** Decide it when you design the effect, before you build it: write down which in-world parts carry it
(light, debris, sparks, dust, heat, the object's own material) and check that none of them is a ring, circle, halo or
outline drawn around the object. Then [the visual checklist](../checklists/visual.md) item 5c (Art language), and the
PR's `Art language:` line. For a glow, change the
emissive colour or intensity on the object's own material (a property block or a material
instance), not a new child sprite or mesh that sits around it. Name the reference asset and
attach the side-by-side still in the PR's `## Evidence` (the `Intended look` line or the
`Shots:` line). If you think the brief really wants an indicator, quote where it says so.
New hero art (a model, an end-game or siege weapon's VFX) also has to be creative, detailed and different from the
existing weapons' effects: [hero art is creative and detailed](visual-fixes-are-verified-by-looking.md#hero-art-is-creative-detailed-and-different-w1470-w1466) (w1470, w1466).

### A glow's colour on screen is measured, not read off the HDR value (w1066)

**Rule.** Before you report a glow's colour ("redder", "more like the Guardian's seams"), measure
it where the player sees it: crop the glow in a built-player still and average the lit pixels
(red, green, blue and green over red). Compare that number with the reference and with the last
round. The HDR value you typed is not the colour on screen.

**Why.** On thin, bright emissive lines the hue comes from intensity, not from the HDR ratio: past
a point the red channel clips through bloom and the tonemapper, and the small green share decides
the hue. w1066 measured it in one scene (green over red of the lit pixels): HDR red 4.6 read 0.58,
3.0 read 0.62, 2.0 read 0.50, 1.3 read 0.36. Round 4's (4.4, 0.55, 0.38) was "pink" on paper and
measured warm orange (239, 173, 102) in the built player; three later rounds changed the HDR ratio
and the screen colour hardly moved. Ben said "not red enough" again and again ("the lines arent red
enough, push it more towards what the guardian looks like with its molten effect actually").

**How to apply.** Keep green out of a red glow's HDR colour (any green share reads orange, blue reads pink), and set
the intensity by whether it glows (next section), not by the hue: a lower intensity is redder but stops glowing. Put
the measured mean colour of the lit pixels, before and after, in the report and the PR's evidence.

### A glow is measured against a glowing reference in the same frame (w1323)

**Rule.** Before a glow change goes to the requester, put the thing and a reference glowing structure (a powered
mass driver) in the same built-player frame at normal zoom and measure both with the game repo's
`scripts/feel/glow_compare.py`: the share of each crop's hot pixels in the glow's hue (luma 200+, 45 over their
surround) and their contrast, with the crops side by side at 1:1. The glow reads like the reference's when the share
and contrast are comparable. An impression from stills is not this check.

**Why.** w1323 sent Ben two rounds of red glow lines on the new assemblers that a look at the stills said were there.
He saw none: "you just didn't add any red glow lines. I don't know why you aren't understanding what I'm asking.
Almost all the structures in final factory have these glowy lines". Measured afterwards, the lines had 0.2-0.3 % hot
red against the mass driver's 3-5 % cyan: faces 0.12-0.33 units wide (1-2 px at normal zoom), on the tier paint, at
HDR 1.9-2.2, peaking at the lit body's own brightness (luma about 117 against 235), so they read as red paint. The
w1066 advice to lower the intensity for a redder hue had set them there.

**How to apply.** Copy the method the game's glowing structures use, measured from their meshes: glow inserts 0.5-0.9
units wide seen from above, set against steel or black, at HDR 5-8 and up (mass driver `_EmissionAG` (0, 8, 3.7)), so
the core goes white-hot and the bloom carries the colour; the same white core with a coloured halo is how a red glow
reads too. Under the game's grade a pure red cannot get brighter than about 2.2 without whitening at the core, and
green in the HDR colour turns it orange. Bigger models (the 3x3 tiers) bloom more from the same lines: tune each to the
reference's share, and look for a haze over the body (w1323: 6 hazed the 3x3 bodies, 4 stopped glowing, 5 matched). A
red glow washes a green body to grey (red and green cancel); measure the body colour under the glow too. Take the
stills in a run without `-ffFeelFrames` capture: with it on, the player's screenshot came back with a flipped copy of
the frame drawn into it.

## Hero art is creative, detailed and different (w1470, w1466)

**Rule.** Before a new **model** or a **hero VFX** (an end-game or siege weapon's projectile and impact, a boss, a
signature ship or building) goes to Ben:

1. **2 or 3 clearly different concepts come first, not one.** Different silhouettes or ideas, not three colourings of
   one. Say in a line what each is; Ben picks or redirects.
2. **A literal real-world object is reinterpreted for space and sci-fi.** If the idea is a bow, a disc, a lance, a
   cannon or a shield, build what it would be as a space weapon (an energy-loaded frame, a field, a tether, a rail of
   light): keep the idea, not the object's shape. Test: would a player who did not read the name see "a bow" or "a
   disc" at once? Then it is too literal.
3. **The model's detail is compared with the game's best models of the same class, side by side in one still.** Same
   camera, lighting and bloom, the new ship or building next to the best existing ones of its class (the most
   detailed battleships or siege ships; the Railgun and other detailed powered buildings), named in the evidence.
   Judge panel lines, greebles, mass, silhouette breaks and emissive accents. A model that reads as a flat primitive
   set beside them is not shown.
4. **A new weapon's projectile and impact are compared with the existing weapons' and read clearly different.** Put
   them next to the Railgun's, the Plasma Bolt's and the others' at the same zoom and say what differs in shape,
   colour, motion and duration. **Any reuse of another weapon's effect (its orb, flash, shockwave, spark burst) is
   named as reuse** and justified or replaced; unnamed reuse is a miss.
5. **The gate's verdict says what makes the piece distinctive**, in a sentence a player could repeat ("the Lance is a
   tether of purple light that pulls the target in; the impact folds the hull inward"), not only "passes the
   art-language check". If you cannot write it, the piece is generic: go back to step 1.

This stacks on the art-language rule above: that asks "does it belong to the game"; this asks "is it good enough for
its role".

**Why.** Ben corrected the same kind of miss twice on 2026-10-18, on art the worker had passed and the orchestrator had
let through.

- **w1470, Singularity Lance (PR #1921).** A flat black disc over a purple disc, with the Plasma Bolt orb reused as the
  projectile. Ben: "I don't like that it's just like a black disc sitting on top of the purple accretion disc ... this
  is the end game weapon that needs to look really cool ... be creative with this."
- **w1466, Urso Ballista siege ship (PR #1929).** A ship built as a bow and arrow, with an impact that looked like the
  others. Ben: "i dont like that its so explicitly like a bow and arrow. we are in space, so you can use this concept
  but be more creative and futuristic, and the model itself is not detailed enough. we need high quality models" and
  "can we get more creative on the impact effect? it looks samey with all the other effects, especially the railgun
  effeect".
- **w1475, Station Shield Generator effect (PR #1924), after the rule above was merged (PR #247).** Too heavy and too far
  from the ship. Ben: "i dont like the shield effect so far: make it more subtle and tighter to the ship itself, with
  more translucence, ethereal, sci fi, liquidy, effect. be creative and be more high quality (but performant)". The
  third correction of one kind in a day, so the rule became a tool check (below).

All three passed because the checks asked "is the requested thing there, in the game's colours?" and never "is it the best
idea for it, as detailed as our best, and different from what we already have?". One take was built and polished;
nothing forced a second concept, a reinterpretation, a detail comparison, or a comparison of the impact with the other
weapons'. Two corrections of one kind in a day, so it is now [checklist item 5e](../checklists/visual.md).

**How to apply.** At design time, before building: write the 2 or 3 concepts (one line each: the literal object it
starts from and what it becomes in space) and, for a weapon, list the existing weapons' effects you must differ from.
Show Ben the concepts (a still of each, or a quick block-out) and build the one he picks, or the strongest if he said to
decide. Before the preview: the one detail still against the named reference models, the projectile and impact next to
the Railgun and Plasma Bolt, the reuse list and the distinct-because sentence. The PR's `## Evidence` carries a `Hero
art:` line naming the concepts offered, the detail reference models, the weapons compared and the distinct-because
sentence; a hero asset without them is not shown and not merged.

**Publish the concepts before any build-quality clip (w1497).** The 2 or 3 concept stills go to the person first
(`publish_review`, stills of each concept or a quick block-out) and the build starts after the pick. A polished
built-player clip of one unreviewed take is the miss: the person then reacts to the clip, not to the idea.

**After the pick, offer a Live view session (w1498).** Ben, w1498: "why dont we test out the live editor for some of this
new art and vfx?" and "keep in mind the knobs arent as important as me just being able to iterate conversatoinally with
the agent to improve the art model or vfx". Once he has picked a concept, offer him a Live view session on it in its real
scene with the game's lighting, and in the session make whatever change he describes (shader code, material, VFX Graph,
mesh or model, a new layer), saying roughly how long each takes (a shader edit shows in seconds, a C# change takes
minutes), with preset knobs as optional extras. What updates without a reload is in the game repo's
`Documentation/Live-View-Knobs.md`; the how-to and the measured round trips are in the project-memory page
[live-view-asset-iteration](../../project-memory/memories/live-view-asset-iteration.md). The final values then go through
the normal PR flow with the `Hero art:` line and a smooth built-game clip, and the Live view and the editor are stopped.

**The tool check (w1497).** `pr_evidence.py` fails a game-repo PR that adds a model or effect art without a filled
`Hero art:` line ([merge checklist](../checklists/merge.md) has the format). What counts is decided from the PR's
changed files with their status (`gh pr view --json files`: `changeType`, additions, deletions): a model file
(fbx, obj, blend, glb, gltf, dae) that is added; effect art (the `EFFECT_ART` paths: VFX or Effects folders, `.vfx`,
`.shader`, `.shadergraph`, `.mat`, Particle) that is added or rewritten by 40 or more changed lines. Not counted:
third-party packs (`ExternalAssets`, `GabrielAguiarProductions`, `SineVFX`, `Vefects` and the other asset-pack
folders), scripts, tests, editor code, UI, icons, sprites, textures, holograms, fog and outlines, an edited model (a
re-export) and a small material tweak. The 40-line threshold and the exclusions are guesses, calibrated on the 300 game
PRs merged since 2026-10-01: 8 trigger (the comet tail, the circuit wire, the map arrow, the Urso Cannon, the
Assemblers and similar), and the three corrected PRs (#1921, #1929, #1924) all do. The line must have five parts, each
filled and not a placeholder: `concepts:` (two or more still files and who picked which), `detail:` (what it was
compared with, one still), `differs:` (from the existing weapons' and effects', with "no reuse" or what it reuses),
`distinct:` and `cost:` (a measured number with a unit, not "expected"). `Hero art: n/a (<reason>)` is allowed with a
reason naming a bug fix, tweak, re-tint, icon, re-export or third-party import, and it shows in the verdict as "HERO ART
SKIPPED"; for an added model or effect file only a rename, move, re-export or third-party import is accepted.
A script cannot tell whether the concepts were different or the detail is enough: the reviewer reads the stills against
[checklist 5f](../checklists/visual.md).

## Review media goes inline, never as a bare path (w1384)

**Rule.** When a person has to look at a still or a clip (a look to OK, a before/after, a preview video), each file
goes into the message they read as its own `![name](<absolute path>)` line. FF Factory's page shows a PNG, JPG, GIF or WebP
inline and an MP4, WebM or MOV as a player (`/api/image`; review files are under the review folder, `/srv/fff/review/<topic>/`
on the portal). That holds for a worker's report, an orchestrator's relay, a `[needs you]` answer, a PR description the
person reads in chat, and a dispatcher question.

- **A folder is its files.** `/srv/fff/review/w1182-fog-look-v4/` is one `![..](<..>)` line per clip and still in it,
  newest version first, never the `.preview/` encodes beside them.
- **A bare name is a path.** `clip.mp4` or `![clip](<clip.mp4>)` is its absolute path under the review folder.
- **A wildcard is its matches**, each its own line.
- **Never a path in backticks or plain text as the way to see it.** A path may appear as well (to find the file), but
  only beside the inline line.

**Why** (w1384). Ben, 2026-10-13 (w1058 and w1061, preview 2): "you have to inline preview videos in this chat for me
to verify them". Ben, 2026-10-15, after his orchestrator relayed a `[needs you]` question for w1182 whose only pointer was
`/srv/fff/review/w1182-fog-look-v4/`: "I need to see the preview video for the fog. Stop giving me paths to videos and
inline the videos like you should be doing and I've reminded you as such like 100 times".

The same miss happened twice in one day, two ways:

- w1182: the dispatcher's question named only the folder. w1378's `[needs you]` builder passed the folder through as
  code, and the orchestrator relayed it.
- w1241: the digest built its files from a kept report that FF Factory clips in the middle. `glow_800_closeup.jpg`
  became `glow_800_closeup.jp`.

The rule had been in the orchestrator's brief all along, and it did not hold. So FF Factory now resolves review paths on
its disk (`server/reviewMedia.ts`): folders become files, bare names become absolute paths, cut-off names become their
folder's files. It also puts inline what a person's orchestrator names bare (ff-factory PR for w1384, docs/orchestrators.md
"Review media inline"). That is a backstop: write it inline yourself.

**How to apply.**

- Writing a report: publish with `publish_review`. Its answer gives the absolute paths. Put each file in as `![what it
  shows](<path>)`, not the folder.
- Relaying (an orchestrator, the dispatcher): copy each `![..](<..>)` line from what you relay. If you were given a
  folder or a bare name, turn it into the file lines before you send. FF Factory's `[needs you]` already lists them that
  way.
- Before you send, run the check in [done.md](../checklists/done.md) item "Review media inline": any review path, folder,
  wildcard or `.mp4`/`.png`/`.jpg` name in the message that is not inside `![..](<..>)` is a miss.

## A clip with a system dialog over the game is void (w1742)

Before a clip or still is published, open a frame of each (its first, a middle and its last frame, or the contact
sheet) and look for anything that is not the game. A Windows Firewall "allow access" prompt, UAC, a crash or a "not
responding" box drawn over the game voids the capture: re-take it once the dialog is gone. A firewall prompt over a
slot player also goes in the report with `player_slots.py firewall`'s output
([the listener rule](clean-up-after-yourself.md#a-listener-binds-127001-or-runs-from-a-stable-path-never-from-tmpdir-w1742)).
On 2026-10-22 an "allow finalfactory.exe" prompt for BEAST's slot2-0 covered all 12 of w1722's review clips, and they
were published that way.
