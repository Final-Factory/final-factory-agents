# Done: before you report a request finished

For a worker about to end a report with `DONE: wNNN`, or to say a request is finished. Every line
holds, or the report says what is left instead of DONE.

1. **Merged.** Every PR of the request merged (verified and CI green;
   [merge your own pull request](../lessons/merge-your-own-pr.md)), its `## Evidence` checked
   ([merges](merge.md)).
2. **The brief's Done, item by item.** Every check the brief's "Done" or "Done when" names ran and
   passed (a live SP or MP run, a built-player still, a paired audit); one that did not is "still
   open", whatever the PR's "Not verified" says. A failed run is explained with evidence (`git
   merge-base --is-ancestor <fix> <build>`, the fixture fixed and rerun), never waved off (w704:
   DONE on unit tests, reopened when the live run read 0 of 100).
3. **Steps after the merge.** Each step the brief asks for after the merge (a paired audit, a
   release's first-hour check, the patch notes posted) ran, and the report says how it went
   ([say DONE per request](../lessons/say-done-per-request.md)).
4. **Clean-up.** Everything you made on disk for this request is removed: player builds, Captures,
   recordings and screenshot sets (after publishing the proofs the report links), worktrees and
   clones you added, save copies in the shared saves folder, scratch outside your own temp folder,
   and the player slots you filled (`python scripts/nightly/player_slots.py prune` empties every
   slot nobody holds). The report says what went and how many GB it freed. If the disk is still
   short, the report says so, and FF Factory's own leftovers you found are already removed, not
   asked about ([clean up after yourself](../lessons/clean-up-after-yourself.md)).
   **Unity batch builds** you started (`-batchmode`, a build or test run) have ended: `unity-slot status` shows none of
   yours, and a stuck one is cleared with `unity` `clear_batch`, not left running
   ([clean up after yourself](../lessons/clean-up-after-yourself.md), w791).
5. **Labels and ids.** Each number and recommendation is labelled measured, sourced or guess, and
   every id has its plain words beside it ([say what an id is](../lessons/say-what-an-id-is.md)).
6. **Open waits.** Every `wNNN: still open:` line that names a person (a reboot, a login, a decision, an
   approval) was declared with `waiting_on_person` before the turn ended, and no `wake_me` stands in
   for it ([a wait on a person is declared, not polled](../lessons/a-person-wait-is-declared-not-polled.md)).
7. **A Deck-facing fix names its real-Deck status** (w770). A change a Steam Deck player meets (glyphs, Steam Input,
   launch resolution, Deck UI, touch) is reported "verified on a real Deck" (who, Steam client and SteamOS versions,
   what they saw) or "not verified on a real Deck: <what stays open>", never a bare done on a tour
   ([the Deck list](deck.md), [a simulated Deck is not a Deck](../lessons/verify-ui-with-full-content-like-a-player.md#a-simulated-deck-is-not-a-deck-w770)). When the
   request is a player's report from their own Deck, DONE waits for their check: end with `wNNN: still open: waiting on
   <name> to check on the Deck` and declare it with `waiting_on_person`.
8. **Steps handed to a person.** Every "someone has to run X" in the report or a question was checked
   against the tools: nothing the ops worker or ssh can do is left to a person
   ([never hand a person a step a tool can do, first section](../lessons/a-person-wait-is-declared-not-polled.md), w855).
9. **Learned.** The report has `Learned: <file or PR>` or `Learned: nothing new`. A correction or a
   reopen gets the check that would have caught it ([lessons belong in the harness
   repo](../lessons/lessons-belong-in-the-harness-repo.md)).
