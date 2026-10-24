# Done: before you report a request finished

For a worker about to end a report with `DONE: wNNN`, or to say a request is finished. Every line
holds, or the report says what is left instead of DONE.

1. **Merged.** Every PR of the request merged (verified and CI green, the game repo's `Test in editmode`, which on a PR runs only the touched tests;
   a master batch that names your PR afterwards reopens the work as an urgent revert request, w1180;
   [merge your own pull request](../lessons/merge-your-own-pr.md)), its `## Evidence` checked
   ([merges](merge.md)).
2. **The brief's Done, item by item.** Every check the brief's "Done" or "Done when" names ran and
   passed (a live SP or MP run, a built-player still, a paired audit); one that did not is "still
   open", whatever the PR's "Not verified" says. A failed run is explained with evidence (`git
   merge-base --is-ancestor <fix> <build>`, the fixture fixed and rerun), never waved off (w704:
   DONE on unit tests, reopened when the live run read 0 of 100).
   A built-player run counts only from the player you launched: its pid from your `launch --detach`, its session
   file from `player_slots.py mine` ([w1856](../lessons/research-the-route-before-you-say-cant.md#drive-only-the-player-you-launched-w1856-2026-10-23):
   the newest session file was another worker's player).
3. **Steps after the merge.** Each step the brief asks for after the merge (a paired audit, a
   release's first-hour check, the patch notes posted) ran, and the report says how it went
   ([say DONE per request](../lessons/say-done-per-request.md)).
4. **Nothing to clean up (w913).** You made your files in `$TMPDIR` and left them: the daemon removes the temp folder, the
   sandbox's build and capture output and the rest ([workers do not clean up](../lessons/clean-up-after-yourself.md)). There
   is no `rm`, `Remove-Item` or `player_slots.py prune` in the work and no "removed N GB" in the report. What the report links
   is published (`publish_review`, `specs/<NNN>/proofs/`) and every clone you need is pushed.
   No runtime of yours ran from `$TMPDIR` while listening (a node or python copy unpacked there): everything you started
   bound 127.0.0.1 or ran from a stable path such as PATH's node and the player slots, so no firewall prompt was raised
   ([lesson](../lessons/clean-up-after-yourself.md#a-listener-binds-127001-or-runs-from-a-stable-path-never-from-tmpdir-w1742), w1742).
   Every delete you did run was strictly inside the machine's worker install folder (`$FF_WORKER_ROOT`); what lies outside it you measured and
   reported with sizes, plus the list of what makes FF Factory write there, and did not delete, whatever the brief said. On Windows you
   read, measured and deleted nothing off the install folder's drive, C: above all, and the report says you did not look there
   ([lesson](../lessons/clean-up-after-yourself.md#windows-disk-work-stays-on-the-install-drive-never-c-w1755), w1755)
   ([the delete checklist](delete.md), [delete only inside the worker root](../lessons/clean-up-after-yourself.md#delete-only-inside-the-workers-install-folder-outside-it-measure-and-report-w896), w896).
   A clean-up request: every folder of another worker you deleted was a DELETE row of `ff-leftovers folders`, and the report lists the KEEP rows with
   their request ([the rule](../lessons/clean-up-after-yourself.md#a-clean-up-never-takes-the-folders-of-a-request-that-has-not-closed-w1379), w1379).
   **Unity batch builds** you started (`-batchmode`, a build or test run) have ended: `unity-slot status` shows none of
   yours, and a stuck one is cleared with `unity` `clear_batch`, not left running
   ([clean up after yourself](../lessons/clean-up-after-yourself.md), w791). **No runaway process**: nothing of yours is
   looping or writing a huge `.output` file ([clean up after yourself](../lessons/clean-up-after-yourself.md), w899).
   **Nothing you started still runs** (w1196, w1197): `ff-leftovers list` shows nothing of your session, or you ended
   what it listed (game players, Xvfb and its window manager, ffmpeg, background jobs, servers) and the report says
   what. **No `ff-leftovers end` until `grep -c FF_LEFTOVERS_CALLERS "$(command -v ff-leftovers)"` prints 1 or more**:
   before FF Factory's w1222 fix it ended the worker's own Claude process on Windows; end what `list` shows by pid
   ([not `end` before the w1222 fix](../lessons/clean-up-after-yourself.md#not-ff-leftovers-end-before-the-w1222-fix)). Every player you started had a quit timer (`-ffSoloQuitAfterSeconds`). A run you keep going while you
   are stopped has a `wake_me` check-in set for it. Biscuit, 2026-10-13: two headless players of closed requests (w1072,
   w1025) ran 27 h and 34 h on about 6 cores at 100% fans, and nobody's report had said they were still up
   ([processes you started end before DONE](../lessons/clean-up-after-yourself.md#processes-you-started-end-before-done-w1196-w1197)).
5. **Labels and ids.** Each number and recommendation is labelled measured, sourced or guess, and
   every id has its plain words beside it ([say what an id is](../lessons/say-what-an-id-is.md)).
   **Quotes are copied, not recalled** (w1399): `python quote_check.py <report or PR body> <the files it quotes>...` lists
   every quoted piece that is not word for word in its source (the brief, the person's words, the reports you cite). Copy
   the source's words or drop the quote marks. w1399's draft proof had Ben asking for "making the add stop button look
   nicer", which he never wrote (his words: "stand out just a little more"), and four critic quotes retyped from memory.
   **Review media inline** (w1384): every still and clip the person must look at is its own `![name](<absolute path>)`
   line. Scan the report for review paths (`/srv/fff/review/…`), folders, wildcards and `.mp4`/`.png`/`.jpg` names: one
   not inside `![..](<..>)` is a miss, and a folder is each of its files, newest first, never `.preview/`
   ([review media goes inline](../lessons/visual-fixes-are-verified-by-looking.md#review-media-goes-inline-never-as-a-bare-path-w1384)). Ben, 2026-10-15: "Stop giving me paths to
   videos and inline the videos like you should be doing and I've reminded you as such like 100 times".
6. **Open waits.** Every `wNNN: still open:` line that names a person (a reboot, a login, a decision, an
   approval) was declared with `waiting_on_person` before the turn ended, and no `wake_me` stands in
   for it ([a wait on a person is declared, not polled](../lessons/a-person-wait-is-declared-not-polled.md)).
   Not already answered: the request's notes and those of the other requests you hold have no answer from that person
   since you raised it, and one question for several requests is one declaration with no `request`
   ([never ask what they already answered](../lessons/a-person-wait-is-declared-not-polled.md#never-ask-a-person-what-they-already-answered-w1812), w1812).
   Every other wait left open is a harness timer (`wake_me`, `blocked_on`, `set_timer`), never a background shell
   loop, `nohup`, `&` or Monitor left to finish it ([a wait is a harness timer](../lessons/a-person-wait-is-declared-not-polled.md#a-wait-on-a-machine-is-a-harness-timer-never-a-background-loop-w1106), w1106).
   No `still open:` line waits on the orchestrator or the dispatcher for your own work: a two-machine or pair check, a
   build, a test run or your CI you run yourself; a check that needs two or more computers at once is `request_pair`, whose
   legs start together while your sandbox is freed, never a sandbox held for a second machine's worker (w1945); files or results
   another request's worker makes for you are `blocked_on` with `reports` ([your own checks are yours](../lessons/a-person-wait-is-declared-not-polled.md#your-own-checks-are-yours-never-wait-on-the-orchestrator-for-them-w1841), w1841).
7. **A Deck-facing fix names its real-Deck status** (w770). A change a Steam Deck player meets (glyphs, Steam Input,
   launch resolution, Deck UI, touch) is reported "verified on a real Deck" (who, Steam client and SteamOS versions,
   what they saw) or "not verified on a real Deck: <what stays open>", never a bare done on a tour
   ([the Deck list](deck.md), [a simulated Deck is not a Deck](../lessons/verify-ui-with-full-content-like-a-player.md#a-simulated-deck-is-not-a-deck-w770)). When the
   request is a player's report from their own Deck, DONE waits for their check: end with `wNNN: still open: waiting on
   <name> to check on the Deck` and declare it with `waiting_on_person`.
8. **Tests tagged right** (w1690). A new or touched test that asserts on time carries `[Category("Performance")]` and
   asserts nothing functional; a functional test does not carry it. A mis-tagged or mixed test you met is fixed in this
   change or its own small PR, a mixed one split so its functional asserts keep running in CI
   ([a timing test is tagged Performance](../lessons/verify-simulation-at-a-slow-hosts-frame-rate.md#a-timing-test-is-tagged-performance-and-checks-nothing-else-w1690-2026-10-21)).
8. **Steps handed to a person.** Every "someone has to run X" or "Ben needs to ..." in the report, a question or a
   `still open:` line was checked against the tools: nothing you, the ops worker or ssh can do is left to a person.
   Closing, opening or restarting Unity (a person's editor on a main clone too: save its scenes or back up, close it,
   do the work, reopen it), git commands, copying files and installers are yours. Left to a person: approvals, design
   decisions, spending, publishing and admin acts that need their own words
   ([never hand a person a step a tool can do, first section](../lessons/a-person-wait-is-declared-not-polled.md), w855, w935).
   Every "can't", "not possible", "no agent can" or "you can ... yourself" names the route you researched (the sources),
   the try or the filed request (its wNNN), and, for what is left, the blocker's evidence (the error, a screenshot) and
   the one smallest step only the person can take (their own login, password or 2FA code, an approval)
   ([research the route before you say can't](../lessons/research-the-route-before-you-say-cant.md), w935, w1287).
8a. **Where a player-facing fix ships, and every build claim run** (w1770). A fix players see names the Steam branch
   and build that carry it, or the bump that will, in a `Ships in:` line, and whether the pre-1.0 line needs a
   cherry-pick in a `pre-1.0:` line (`cherry-pick needed (<wNNN or PR>)`, `#<PR>` for one you opened, or `not needed:
   <why>`): master is the 1.0 build on `development`, pre-1.0 the line default-branch players get until 1.0 ships.
   Every "is in", "has", "contains", "missing" or "not in" beside a build number, version or Steam branch in the report
   rests on a run of that build or its exact commit with the feature opened (what you ran, what you saw), or says guess
   and names the build to run; a grep, `git merge-base` or a past report is not a run. `python build_claim_check.py
   <report> --done` checks both ([what is in a player's build is checked by running
   it](../lessons/whats-in-a-players-build-is-checked-by-running-it.md)). Ben, on #1760's tabs called done on master
   and then "in Build 111" from git: "so you're lying to me, or you didn't actually check".
9. **Every bug thread.** A request to sweep, triage or cover bug reports has one row per #bug-reports and dev_bug_reports
   thread created or active in its window, read from the full thread list (FF Factory's `bug threads: coverage` journal
   lines, or the channels themselves), never from titles someone picked; and every thread where an owner acknowledged
   the bug, in any words, has a request whose subject it is
   ([every bug thread has an owner](../lessons/a-fix-pr-names-its-reports.md#every-bug-thread-has-an-owner-w1783-2026-10-22), w1783).
10. **Learned.** The report has `Learned: <file or PR>` or `Learned: nothing new`. A correction or a
   reopen gets the check that would have caught it ([lessons belong in the harness
   repo](../lessons/lessons-belong-in-the-harness-repo.md)).
   A GitHub 403 or "Resource not accessible" you met on a person's or the portal's token, for a permission or repository
   not in ff-factory's `shared/githubRequirements.ts`, was added there and to docs/vault.md 13.2 in a merged PR, named in
   the report (Checks and repositories outside Final-Factory excepted; [lessons belong in the harness
   repo](../lessons/lessons-belong-in-the-harness-repo.md), "A GitHub refusal becomes a requirement", w904).
