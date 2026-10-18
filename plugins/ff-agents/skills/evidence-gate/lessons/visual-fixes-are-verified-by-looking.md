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

Both passed because the checks asked "is the requested thing there, in the game's colours?" and never "is it the best
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

**Not automated yet.** `pr_evidence.py` cannot tell a hero asset from other new art (it sees changed shader, material
and VFX files, not a new model's role), so this rests on the checklist and on the orchestrator reading the report. On a
third correction of this kind, add a `Hero art:` field check to `pr_evidence.py` with the w1470 and w1466 PR bodies as
fixtures.

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
