# Visual changes: what "verified" means

For any change a player sees: VFX, shaders, animation, particles, camera feel, UI, where something
is drawn. The recording and review recipe is the `watch-video` skill; this list is what has to be
true before the change merges or is reported as fixed.

0. **Who else draws with it.** Before you edit a shader, shader graph, subgraph, include or
   material, run `python3 scripts/asset_usage.py <path>` in the game repo. Anything besides the
   target on the list: give the target its own shader or material, or put every user in scope and
   show a built-player before/after of each kind. The PR's `## Used by` section lists them
   ([lesson](../lessons/check-who-uses-a-shared-asset.md); w410 darkened every range ring).
1. **The intended look, in the person's words.** Quote what they said ("the other player appears
   outside of the ship behind it"). If they have not said, write it yourself and say it is yours.
   A review against your own description of a mistake will pass the mistake.
2. **A built player, and the real event.** Launch it from the slot pool and reach the event the
   way a player does: the real hit, the real deconstruct, the real second rider. An editor rig or
   a hand-set state shows that the code runs, not that the game looks right. If a built player is
   impossible, say so: the change is then "changed, not yet seen in the built game", not "fixed".
3. **Before and after clips at 60 fps** that cover the effect's whole life (`record_clip`).
4. **The clip contains the event.** Name the frames or seconds where it happens. A clip without
   the event proves nothing, and a review of it is void.
5. **Look yourself.** Step through the event's frames (`frames.jpg`) against each line of the
   intended look, at a zoom where the detail shows. Position numbers, counts and logs support
   this. They do not replace it.
6. **`watch_video` and the blind model review are a second opinion.** They have passed clips
   that did not contain the event, and agreed with a mistake the brief described as intended.
   Quote them, and say where the frames contradict them.
7. **No merge before the review is finished.** "Pending" is not finished.
8. **Report what you saw.** Say which frames you looked at and what they show. If the person
   reported the bug or has caught it before, put the clip in your report so they can watch it.

**Where review media goes** (w309, Lothsahn 2026-10-03): publish the stills, clips and review report with FF Factory's `publish_review` tool (`mcp__sandbox__publish_review` in a BEAST sandbox, `mcp__machine__publish_review` on a machine; `topic`, `files`, `note`). It puts them in the review folder on BEAST (`F:\ffsb\_review\<topic>\`) and answers the paths to put in your report and the PR. Never ssh, scp or copy review files across machines. A session without the tool (FF Factory not yet updated) keeps them in its worktree, lists the local paths, and says they are not published.

In a pull request these go into `## Evidence` (the format is in [merge.md](merge.md)).

Lessons behind this list:
[a visual fix is verified by looking](../lessons/visual-fixes-are-verified-by-looking.md),
[no merge before the review](../lessons/no-merge-before-the-review.md).
