# Visual changes: what "verified" means

For any change a player sees: VFX, shaders, animation, particles, camera feel, UI, where something
is drawn. The recording and review recipe is the `watch-video` skill; this list is what has to be
true before the change merges or is reported as fixed. **A screen, panel, tab, HUD element or
layout also follows [the UI checklist](ui.md)**: a late-game save, every sub-view, the whole
content, the classic look side by side, a real-rate clip for flicker (w718: the w644 hub passed
on stills and broke on Ben's Deck).

A **mouse cursor** change is the exception to "on video": no capture contains the OS cursor, so it is read from Windows
in the built player (drive-game, "The mouse cursor in a built player"; w980).

0. **Who else draws with it.** Before you edit a shader, shader graph, subgraph, include or
   material, run `python3 scripts/asset_usage.py <path>` in the game repo. Anything besides the
   target on the list: give the target its own shader or material, or put every user in scope and
   show a built-player before/after of each kind. The PR's `## Used by` section lists them
   ([lesson](../lessons/check-who-uses-a-shared-asset.md); w410 darkened every range ring).
0b. **What else goes through the code.** A change to shared presentation code (selection and
   hover boxes, highlights, outlines, icons, health bars, panels) is checked on every kind of
   object that code draws, moving, rotating and spinning ones included, not only the case you
   fixed. A component that picks out one kind is counted in a running game against every
   archetype that carries it. Film at least one other kind in the before/after, and name any
   kind left out under "Not verified"
   ([lesson](../lessons/check-every-kind-of-object-shared-presentation-draws.md); w453 turned
   every `Placeable`'s box with it, so comet fragments' boxes spun).
0c. **Measure against what the player sees.** A placement metric's reference is the drawn thing
   (the hull's surface or outline, the drawn position this frame), computed independently of the
   code under test, never the place the code meant to put it (the simulated hit point, the fix's
   own value). Sweep every kind of target and pose, and show the metric reading badly on the
   "before" arm ([lesson](../lessons/measure-against-what-the-player-sees.md); w176 scored impacts
   against the simulated hit, read 0.0 u, and they landed inside the hull).
0d. **Moving things are filmed moving, and the clips are checked first.** A change to how something moving is drawn is
   measured on free-flowing things: parked ones (a backed-up belt) are drawn at their simulation position and look the
   same before and after. Look at each clip's first still (is it the game?) and its `ffprobe` size before you
   take a number from it ([lesson](../lessons/measure-against-what-the-player-sees.md); w1086).
1. **The intended look, in the person's words.** Quote what they said ("the other player appears
   outside of the ship behind it"). If they have not said, write it yourself and say it is yours.
   A review against your own description of a mistake will pass the mistake.
2. **A built player, and the real event.** Launch it from the slot pool and reach the event the
   way a player does: the real hit, the real deconstruct, the real second rider. An editor rig or
   a hand-set state shows that the code runs, not that the game looks right. If a built player is
   impossible, say so: the change is then "changed, not yet seen in the built game", not "fixed".
3. **Before and after clips at 60 fps** that cover the effect's whole life (`record_clip`). Stills
   played one a second are not a clip: they cannot show a pop, a flicker or a jump.
   **The game in the clip runs smooth too, measured and stated** (w1325, Ben: "also the video previews are of a game
   that really low fps which makes it harder to evaluate"). A 60 fps file of a game drawing 3-5 frames a second (a huge
   save on a machine other sandboxes load) is a slideshow. Read the capture's own frame times (the feel probe,
   `frames.json` of the game repo's feel scripts) and write the mean fps beside each clip; under 30, re-take on a quiet
   machine or a lighter save that still shows the effect at work (w1325 moved from JustPlay at 3-5 fps to Wittlebase2 at
   45-55 fps), never send it. Each frame is held for its own capture time (`scripts/feel/clip_timing.py`): a cap or a
   rounding to 60ths plays the clip at the wrong speed, and a pulse or a fold then measures wrong.
4. **The clip contains the event.** Name the frames or seconds where it happens. A clip without
   the event proves nothing, and a review of it is void.
5. **Look yourself.** Step through the event's frames (`frames.jpg`) against each line of the
   intended look, at a zoom where the detail shows. Position numbers, counts and logs support
   this. They do not replace it.
5b. **Artifact hunt: what is visible that nobody asked for (w895, w1015).** "Matches the brief" is two
   checks. Besides "is each thing asked for there?", go through every still and every frame of the
   sheet again and write down what is on screen that the brief did not ask for: a duplicate, ghost or
   leftover copy of an object, a dark or unlit silhouette, stale UI, one thing drawn over or
   intersecting another (a hover card over a panel, text over sliders), a z-order error, flicker, clipped
   text. Each is explained (and the person would agree it is meant) or fixed before you write
   "matches"; "nothing extra" is claimed only with the list of what you looked for. A measurement is
   not this pass ([lesson](../lessons/visual-fixes-are-verified-by-looking.md#hunt-for-what-should-not-be-there-w895-w1015); Ben, w895: "the hover
   panel is clearly showing over the defense platform"; w1015: "why is there a black ghost vessel
   that stays behind").
5b2. **No system dialog over the game (w1742).** Before a clip or still is published, open a frame of each (first,
   middle, last, or the contact sheet) and look for anything that is not the game: a Windows Firewall "allow access"
   prompt, UAC, a crash or "not responding" box. One there voids the capture: re-take it after the dialog is gone, and
   **A clip's frames show only the player window** (w2408): a desktop grab (`ddagrab`, `gdigrab`: every Windows clip
   without `gfxcapture`) records any window drawn over the player, a browser or another sandbox's editor, exit 0
   (w2380, BEAST); `record_clip` pins the player and refuses a covered take, so a hand-made `ffmpeg` grab needs the
   same look.
   For a firewall prompt over a slot player run `player_slots.py firewall` and report it
   ([lesson](../lessons/visual-fixes-are-verified-by-looking.md#a-clip-with-a-system-dialog-over-the-game-is-void-w1742); a slot2-0 prompt covered all 12 of w1722's clips).
5c. **Art language: two solid main colours + one bright, bloomy HDR accent, and a highlight is the object's own
   material (w1066, w1241).** New models and materials are compared with an existing reference asset (the Railgun,
   other powered buildings, existing enemy ships) in the same still: same camera, lighting and bloom. A highlight
   on something in the world drives its own emissive/HDR accent or rim light, never a world-space sprite, halo, ring
   or UI-like indicator (unless the brief asks for an indicator). The PR's evidence names the reference asset and
   shows the side-by-side still ([lesson](../lessons/visual-fixes-are-verified-by-looking.md#new-art-matches-final-factorys-art-language-w1066-w1241); Ben, w1066: "you didnt
   add this to the assemblers here"; w1241: "more like a world space UI indicator, isntead of making the ship
   itself glow more naturally"). A glow's colour is reported as measured: the mean of its lit pixels in a built-player
   crop, before and after, because on thin bright lines bloom and the tonemapper set the hue by intensity, not by the
   HDR ratio ([lesson](../lessons/visual-fixes-are-verified-by-looking.md#a-glows-colour-on-screen-is-measured-not-read-off-the-hdr-value-w1066);
   w1066: three rounds of "not red enough").
   **Decide it at design time, before building** (w1332): write which in-world parts carry the effect (light, debris,
   sparks, dust, heat, the object's own material) and that none is a ring, circle, halo or outline drawn around the
   object; Ben, w1332: "again I don't like the unnatural circle effect that looks like UI. The vfx should be part of
   the game world in its appearance". A PR changing effect art carries `Art language:` (the reference compared, and
   no ring/circle/halo/UI-like overlay, or the person's words asking for one); `pr_evidence.py` fails it without.
5d. **A glow is measured against a glowing reference in the same frame (w1323).** A new or changed glow (emissive
   lines, an HDR accent) is put beside a powered mass driver in one built-player frame at normal zoom and measured with
   the game repo's `scripts/feel/glow_compare.py` (hot glow-hue pixels as a share of each crop, their contrast, the
   crops side by side at 1:1) before it goes to the requester; the share and contrast are comparable to the
   reference's, and the numbers and the 1:1 crops go in the report and the PR. Thin glow faces at HDR about 2 read as
   paint ([lesson](../lessons/visual-fixes-are-verified-by-looking.md#a-glow-is-measured-against-a-glowing-reference-in-the-same-frame-w1323);
   w1323, Ben after two rounds that an impression from stills passed: "you just didn't add any red glow lines").
5e. **Hero art: creative, detailed and different, not literal or generic (w1470, w1466).** A new model or hero VFX
   (an end-game or siege weapon's projectile and impact, a signature ship) does not go to Ben as one take. (1) The
   first look is 2 or 3 clearly different concepts. (2) A concept that is a literal real-world object (a bow, a disc)
   is reinterpreted for space and sci-fi. (3) The model's detail is compared, side by side in one still (same camera,
   light, bloom), with the game's best existing models of the same class, and the comparison is named. (4) A new
   weapon's projectile and impact are compared with the Railgun's, the Plasma Bolt's and the other weapons' and read
   clearly different; any reuse of another weapon's effect is called out. (5) The verdict says what makes the piece
   distinctive, not only that it passes. **The concept stills are published to the person before any build-quality clip
   is made** (w1497), and the picked concept is offered a Live view session in its real scene, where you change
   whatever the person describes and they watch it (w1498;
   [how](../../project-memory/memories/live-view-asset-iteration.md)). The PR's evidence carries a `Hero art:` line (`concepts:`, `detail:`, `differs:`, `distinct:`,
   `cost:` measured in a built player), which `pr_evidence.py` fails the PR without when it adds a model or effect art
   ([merge.md](merge.md) has the format; `Hero art: n/a (<why>)` shows in the verdict); a reviewer reads it with 5f
   ([lesson](../lessons/visual-fixes-are-verified-by-looking.md#hero-art-is-creative-detailed-and-different-w1470-w1466); Ben, w1470, Singularity Lance: "I don't like that it's
   just like a black disc sitting on top of the purple accretion disc ... this is the end game weapon that needs to
   look really cool ... be creative with this"; w1466, Urso Ballista: "i dont like that its so explicitly like a bow
   and arrow ... the model itself is not detailed enough. we need high quality models" and "it looks samey with all
   the other effects, especially the railgun effeect").
5f. **Reviewer: read the hero art against its role (w1497).** `pr_evidence.py` checks that the `Hero art:` line is
   filled; you check that it is true, from the stills: (1) **Subtle or heavy**: is the effect as light as it should be
   for what it is (a shield hugging the ship, translucent, not a thick dome; Ben, w1475: "more subtle and tighter to the
   ship itself, with more translucence, ethereal, sci fi, liquidy")? (2) **Generic or creative**: could the concepts be
   told apart at a glance, and would a player who did not read the name see "a bow", "a disc" or a recoloured copy of
   another weapon's effect? (3) **Detail level**: at the same zoom as the named best models, does it hold its own
   (panel lines, silhouette breaks, emissive accents)? (4) The concept stills were published before the build, and the
   pick is the person's. (5) **Scale**: is it in scale with its neighbours, in a built-game still beside them at
   gameplay zoom (5k)? Any "no" goes back before the clip.
5g. **Every "it's gone" and "it happens" is shown close up, against every surface, and asked as a question (w1567).**
   Each sentence in a review note, report or PR that says a visual defect is gone ("no z-fight", "the flicker is
   fixed", "no longer draws through") or that an effect happens ("ships spaghettify", "pulls in the boss", "the disc
   wraps over the core") names its own close-up: a full-resolution (1:1) crop of that exact moment, or a slowed clip
   segment of it (0.25x, with its seconds). A contact sheet, a whole-frame clip or a frame-wide number is not one.
   (1) A z-fight, draw-through or occlusion claim has a crop of the effect's edge over **every surface it overlaps**:
   terrain, structures and hulls, other effects. List them on a `Surfaces:` line; one occluder checked is not "gone".
   (2) An effect on a victim (stretch, pull, fall in) is cropped on the victim, at a size where its shape shows.
   (3) The fresh critic (a new subagent, or watch_video's blind review via `--brief`) gets each claim **as a question**
   with the crops ("At 2.4 s, does the hole draw over the terrain at its left edge?"), never as a statement it can
   agree with. Write `Close-ups: <claim>: <file>; ...` in the note and the PR's Evidence; `pr_evidence.py` fails a PR,
   and `pr_evidence.py --note <note.md> --questions q.md` a review note before `publish_review`, that claims either
   kind without one, writes the questions for the critic, and checks each named file is beside the note
   ([lesson](../lessons/visual-fixes-are-verified-by-looking.md#every-its-gone-is-shown-close-up-against-every-surface-w1567);
   Ben, w1470: "its z fighting in the screenshot with the antimatter nexus or something, and its not pulling in the
   boss", then, after a note said the z-fight was gone: "the units dont really spagettify when they get pulled in and
   also theres still weird z fighting where the blakc hole isnt overtop of the terrain").
5h. **A transition is shown every frame on the object, until its end state (w1686).** A claim that something turns into
   its end state ("stretches into", "is swallowed", "is pulled into", "dissolves", "stays lit as itself", "one smooth
   animation") names, on the `Close-ups:` line, a sheet of **every frame** (every 2nd at 50 fps or more) of the whole
   transition, cropped on the object, from the frame before it starts to its stated end state:
   `uv run transition_strip.py <clip> --from <s> --to <s> --crop W:H:X:Y --claim <name>` (uv installs its numpy and
   Pillow; plain python3 has neither on the Macs) writes it and frames the pop
   candidates in red. In each frame the object's own model is still on screen, a little further along, until the end
   state; one frame where it is gone or replaced early is a pop and the claim is false. A sheet every 0.2 or 0.5 s, a
   still or a 0.25x clip is not this proof: at 60 fps a 0.5 s step shows 1 frame in 30, and a vanish takes about 6. A
   second opinion's "disappears", "at once" or SNAP during the transition is answered with that strip, asked of a fresh
   critic, never explained away. `pr_evidence.py` fails a transition claim without the strip, and a vanish flag beside
   one ([lesson](../lessons/visual-fixes-are-verified-by-looking.md#a-transition-is-stepped-every-frame-on-the-object-and-it-disappears-is-cleared-only-that-way-w1686);
   w1470, the Guardian vanishing mid-swallow: the critic said "the Guardian disappears at once", a sheet every 0.2 s
   cleared it, and Ben: "the guardian especially doesn't really smoothly transition to the spaghetti state it just kind
   of disappears. I want one smoth animation for the model getting stretched and sucked into the black hole").
5i. **No frame where the object jumps or lunges (w1816).** On the same strip, the object moves about as far each frame
   as in the frames around it, all the way to its end state: no frame where it leaps to the hole's centre or across
   the screen, and no creep that turns into a dive (several times its pace within a few frames). Run
   `transition_strip.py` with `--track X,Y` (a point on one object in the first frame), check its green dot stays on
   the object, and look at every frame it frames in orange (JUMP: a move in one frame over 4 times the median move of
   the 6 frames each side and over half its size; LUNGE: over 6 frames, over 3 times its pace of the 30 before). The
   critic is asked "does it jump in one frame, or creep and then lunge? Name the frame." ([lesson](../lessons/visual-fixes-are-verified-by-looking.md#a-transition-keeps-its-place-and-its-colours-w1816); w1685, after the clip passed with "no
   vanish, pop, swap or jump", Ben: "i dont like that it suddenly jumps to the center of the black hole").
5j. **The object keeps its own colours (w1816).** In every frame of the transition the object shows the colours it
   had in its first frames (its hull, its lights), not another hue: no frame where it turns purple, takes the hole's
   colour or is hidden under a tint. A glow the person asked for is named, not assumed (`--allow-hues heat` for a heat
   glow). Look at every frame the strip frames in magenta (HUE: 35% or more of the object's pixels outside its
   first-frame palette); the critic is asked "does it keep its own colours? Name the first frame and the colour."
   ([lesson](../lessons/visual-fixes-are-verified-by-looking.md#a-transition-keeps-its-place-and-its-colours-w1816); w1685, Ben: "and then also becomes that
   purple. it'd be cool if it more smoothly swirled into the black hole and used the objects actual colors with
   perhaps some heat glow effect").
5k. **New or changed world model: built-game still of it beside its existing neighbours (items: on a connector and in
   an inserter hand), at gameplay zoom; its size matches theirs (w2204).** An item, structure, ship, projectile or
   pickup: the still names what is beside it and gives the size verdict (or the ratio and why). A still of the model on
   its own, or an editor preview, does not count. The PR's Evidence carries `Scale: <still>: <model> beside <neighbours>
   at gameplay zoom in the built player; its size matches theirs`, which `pr_evidence.py` fails the PR without when it
   adds or changes a model file or mesh asset, or adds an item, structure or projectile prefab; the fresh critic is
   asked "is it in scale with its neighbours?" ([lesson](../lessons/visual-fixes-are-verified-by-looking.md#new-models-are-checked-at-scale-in-the-game-beside-their-neighbours-w2204); Ben,
   w2204, after #1596's Repair Pack: "the repair pack connector item is comically large. make sure you test these
   visually when you add new models to the game in the future").
5l. **A hide, cull or visibility change: list every visual the thing carries, then count what is still drawn inside its
   bounds in a built game; expect 0 (w2210).** Its children and the separate entities or GameObjects that follow it:
   VFX, particles, shields, engines, lights, trails, outlines, labels, icons, attached items. Take the census with every
   one of them live (shields up, engines firing) and film the hide. The PR's Evidence carries `Hidden census: <census
   log, clip>: with <the thing> hidden in a built player, 0 renderers, particle systems and VFX still drawn inside its
   bounds; it carries <every kind>`, which `pr_evidence.py` fails the PR without when it changes a game script named for
   hiding, showing or culling; the fresh critic is asked "is anything still drawn where the hidden thing was?"
   ([lesson](../lessons/check-every-kind-of-object-shared-presentation-draws.md#a-hide-hides-everything-the-thing-carries-proven-by-a-census-w2210);
   Ben, w2209, after Hide Flying Stations left belt items, then the hover field, then shields and engine effects drawn:
   "hiding mobile stations should hide any shielding they have and the rocket engine effects. and anything else, you
   keep missing stuff").
5m. **A before-and-after of a view that moves with game time is shot at one game heartbeat in both legs (w2469).**
   Fog, moving ships or belts change between seconds: wait in each leg for the same heartbeat (any `ffauto:` answer's
   `heartbeat`), shoot, and write it beside the still; the noise floor is the same build twice, at the same heartbeats.
   A launch poll that answered late shot one leg minutes of game time after the other, and two identical fog paths
   differed by 46.7 against a floor of about 2 ([lesson](../lessons/visual-fixes-are-verified-by-looking.md#a-before-and-after-of-a-view-that-moves-with-game-time-is-shot-at-one-heartbeat-w2469)).
6. **`watch_video` and the blind model review are a second opinion.** They have passed clips
   that did not contain the event, and agreed with a mistake the brief described as intended.
   Quote them, and say where the frames contradict them.
7. **No merge before the review is finished.** "Pending" is not finished.
7a. **An approval ask explains every change, with a cropped, marked pair.** Asking a person to OK a look or behaviour
   change: one section per change with Before (step by step), After, Fixes, Code (file, method, old -> new value),
   Unchanged, and a still pair from `approval_ask.py mark` (cropped to what differs, ringed); `approval_ask.py check`
   passes first, as in the [UI checklist](ui.md) item 35. A clip still goes inline beside the pair.
8. **Report what you saw.** Say which frames you looked at and what they show. If the person
   reported the bug or has caught it before, put the clip in your report so they can watch it.

**How review media is shown** (w1384): each clip and still goes into the report, the relay and the PR as its own
`![name](<absolute path>)` line, which the page plays or shows inline; never a bare path or a folder
([review media goes inline](../lessons/visual-fixes-are-verified-by-looking.md#review-media-goes-inline-never-as-a-bare-path-w1384)).

**Where review media goes** (w309, Lothsahn 2026-10-03): publish the stills, clips and review report with FF Factory's `publish_review` tool (`mcp__sandbox__publish_review` in a BEAST sandbox, `mcp__machine__publish_review` on a machine; `topic`, `files`, `note`). It puts them in the review folder on BEAST (`F:\ffsb\_review\<topic>\`) and answers the paths to put in your report and the PR. Never ssh, scp or copy review files across machines. A session without the tool (FF Factory not yet updated) keeps them in its worktree, lists the local paths, and says they are not published.

In a pull request these go into `## Evidence` (the format is in [merge.md](merge.md)).

Lessons behind this list:
[a visual fix is verified by looking](../lessons/visual-fixes-are-verified-by-looking.md),
[hero art is creative and detailed](../lessons/visual-fixes-are-verified-by-looking.md#hero-art-is-creative-detailed-and-different-w1470-w1466),
[no merge before the review](../lessons/no-merge-before-the-review.md).
