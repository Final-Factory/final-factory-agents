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
6. **`watch_video` and the blind model review are a second opinion.** They have passed clips
   that did not contain the event, and agreed with a mistake the brief described as intended.
   Quote them, and say where the frames contradict them.
7. **No merge before the review is finished.** "Pending" is not finished.
8. **Report what you saw.** Say which frames you looked at and what they show. If the person
   reported the bug or has caught it before, put the clip in your report so they can watch it.

**How review media is shown** (w1384): each clip and still goes into the report, the relay and the PR as its own
`![name](<absolute path>)` line, which the page plays or shows inline; never a bare path or a folder
([review media goes inline](../lessons/visual-fixes-are-verified-by-looking.md#review-media-goes-inline-never-as-a-bare-path-w1384)).

**Where review media goes** (w309, Lothsahn 2026-10-03): publish the stills, clips and review report with FF Factory's `publish_review` tool (`mcp__sandbox__publish_review` in a BEAST sandbox, `mcp__machine__publish_review` on a machine; `topic`, `files`, `note`). It puts them in the review folder on BEAST (`F:\ffsb\_review\<topic>\`) and answers the paths to put in your report and the PR. Never ssh, scp or copy review files across machines. A session without the tool (FF Factory not yet updated) keeps them in its worktree, lists the local paths, and says they are not published.

In a pull request these go into `## Evidence` (the format is in [merge.md](merge.md)).

Lessons behind this list:
[a visual fix is verified by looking](../lessons/visual-fixes-are-verified-by-looking.md),
[no merge before the review](../lessons/no-merge-before-the-review.md).
