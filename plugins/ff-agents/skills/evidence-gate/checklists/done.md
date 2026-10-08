# Done: before you report a request finished

For a worker about to end a report with `DONE: wNNN`, or to say a request is finished. Every line
holds, or the report says what is left instead of DONE.

1. **Merged.** Every PR of the request merged (verified and CI green;
   [merge your own pull request](../lessons/merge-your-own-pr.md)), its `## Evidence` checked
   ([merges](merge.md)).
2. **Steps after the merge.** Each step the brief asks for after the merge (a paired audit, a
   release's first-hour check, the patch notes posted) ran, and the report says how it went
   ([say DONE per request](../lessons/say-done-per-request.md)).
3. **Clean-up.** Everything you made on disk for this request is removed: player builds, Captures,
   recordings and screenshot sets (after publishing the proofs the report links), worktrees and
   clones you added, save copies in the shared saves folder, scratch outside your own temp folder,
   and the player slots you filled (`python scripts/nightly/player_slots.py prune` empties every
   slot nobody holds). The report says what went and how many GB it freed. If the disk is still
   short, the report says so, and FF Factory's own leftovers you found are already removed, not
   asked about ([clean up after yourself](../lessons/clean-up-after-yourself.md)).
4. **Labels and ids.** Each number and recommendation is labelled measured, sourced or guess, and
   every id has its plain words beside it ([say what an id is](../lessons/say-what-an-id-is.md)).
5. **Open waits.** Every `wNNN: still open:` line that names a person (a reboot, a login, a decision, an
   approval) was declared with `waiting_on_person` before the turn ended, and no `wake_me` stands in
   for it ([a wait on a person is declared, not polled](../lessons/a-person-wait-is-declared-not-polled.md)).
