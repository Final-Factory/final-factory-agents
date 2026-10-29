# Releases: before the bump and after it is live

The mechanics are the `ci-release` skill and stay as they are: a release starts only when Ben or
Lothsahn asks, the release run's tests gate the upload, and the notes ride in the bump. This list
adds what a release rests on and the first check after it.

## Before the bump

0. **A or B, or no card.** Before you bring the A-or-B card (`last_green.py`), read the request and its notes: does
   the release follow work items ("release when w1 and w2 are done", "after", "once ... merged", "with the fix for")?
   Then there is no card (lothsahn, 2026-10-29, w2536: "If someone asks for a release after a workitem or set of work
   items, always build off the tip when those work items merge."; "Because they need to have those there."): name
   each item and its merge on `origin/master`, `blocked_on` until they are merged, then bump on master's tip (A). One
   closed without a merged change: ask the person first. A card asked on such a release is a miss (lesson:
   [a release after work items builds on the tip](../lessons/a-release-after-work-items-builds-on-the-tip.md)).
1. **What is in it.** `git log <previous release>..origin/master`, as for the notes.
1b. **Major new content has its go-live moment from the person** (Ben, 2026-10-18, w1453: "You should have
   asked me I need to do a steam event and stuff", after 1.0.0.0 went live on `development` on a plan he had
   agreed). If the build makes major new content live on any Steam branch (1.0, a feature toggle on by default
   through `FeatureToggles.OnByDefault` or shipped in the range, an open beta), name the person's confirmation
   of the moment, in their words from the sender line, for this build. None: stop and ask
   (`waiting_on_person`); an agreed plan is not it. A brief or PR that changes what a Steam branch serves by
   default (a branch cut, a `SETLIVE` change, a version line, a toggle default) carries the same line, or
   "go-live moment not confirmed: ask before the first build". Routine hotfix builds skip this (lesson:
   [ask before content goes live](../lessons/ask-before-content-goes-live.md)).
2. **Every "fixed" in the notes rests on something.** For each player-visible fix, find its pull
   request's `## Evidence`. Looked at in a built player: write "Fixed". Otherwise say what changed
   ("Changed how riders are drawn on a moving station") or leave it out, and tell whoever asked
   for the release which fixes nobody has seen in a built game.
   `pr_evidence.py --audit --since <date of the previous release>` lists them.
   Read every PR's "Not verified:" line in the range: a native or platform call nobody ran on that
   platform goes to whoever asked for the release and into the notes (Build 88 crashed every Steam
   Deck at start-up from `SetInputActionManifestFilePath` under Proton, listed "Not verified" in
   #1249; fixed in #1261).
2b. **The notes are for players.** Only what a player sees and feels: features, fixes, balance,
   performance, platform support. No git branches (master, develop), no dev or branching flow, CI,
   tests, merge queue, FF Factory, FFBox, agents, workers or PRs, and no word on which Steam branch
   follows which git branch (only the standard "Live on the development branch / Restart Steam" lines).
   `python scripts/release_notes_lint.py <notes>` (game repo) exits 0 before the bump and again before
   `post_as_max`; Build 101 told players "Dev builds now come from master" (lesson:
   [notes are for players](../lessons/a-release-is-done-when-its-notes-are-posted.md)).
2c. **Every line is something a release player gets** (Ben, 2026-10-13, w1242: "Mobile stations take their bots
   and barges with them / Isnt this behind a feature toggle?"). A release player has every feature toggle off,
   so a change behind a toggle still declared in `FeatureToggles.cs` at the release commit is not a note.
   `python "$FF_SKILLS/evidence-gate/release_notes_check.py" <notes> --repo <game clone> --range <previous release>..<release>` (beside
   `pr_evidence.py`) lists the toggled PRs in the range and fails on a bullet that matches one, and on workflow
   words (2b). Exit 0 before the bump and before `post_as_max`; read its list of toggled PRs against the notes
   once (lesson: [patch notes list only what players can use](../lessons/a-release-is-done-when-its-notes-are-posted.md#patch-notes-list-only-what-players-can-use-build-104-w1242)).
3. **Saves still load.** The hard rule, as `ci-release` section 0 has it: the golden-fixture and
   layout tests pass in the release run, and a layout change has its upgrade step.
4. **Who asked is on record.** The request for the release, and any hold or lift of a hold, names
   its sender: the message's `[from <name>]` / `[from the orchestrator, for <name>]` line or the
   ledger's requester. Write that name and nothing else; with none, the hold stands and you ask
   (lesson: [name a decider only from the sender line](../lessons/name-a-decider-only-from-the-sender-line.md)).
5. **Write what you expect:** which players build, which branch goes live with which app (read
   `SETLIVE`, never recall it), and the test counts you expect to see.

## After it is live: the first check, within an hour

6. **It is the build you meant, on the branch ffbox actually sets.** `python scripts/release-status.py
   <version>` (game repo) says LANDED, with the BuildID on `development` (a master bump; ffbox
   `release_lane.SETLIVE`, read by the script). `pre-release` and the default branch are set by nothing:
   a person moves them; never propose moving one while the script says BUILDING or
   WAITING (lesson: [where a release lands is read, not recalled](../lessons/whats-in-a-players-build-is-checked-by-running-it.md#where-a-release-lands-is-read-not-recalled-2026-10-03)).
7. **Players are not worse off than on the previous build.** Read, by version and by platform
   (Windows, Mac): the crash and desync reports players' games uploaded for the new version
   (FFBox's intake holds them; an orchestrator sees them with `ffbox_activity`), and new threads
   in the bug channels that name it (`ffdiscord read`). Reading is all you do there; FFBox owns
   those channels. Some failures upload nothing: a crash under Proton never reaches Unity's crash
   handler (Build 88: the player's Player.log in a thread was the only trace), and a slower frame
   files no report (Build 80: idle per-frame work cost about 2.2 ms a frame in a desktop dev player, #1137). Read the
   threads for start-up crashes and slowness, not just the uploads.
8. **Stop and report** when a save does not load, a platform is missing, or reports for the new
   version are clearly above the previous one's. Give the evidence and the previous BuildID.
   Rolling back or promoting a branch is the owner's call; never move a Steam branch by hand.
9. **Patch notes are posted once it is confirmed live**, which means LANDED on the branch the lane sets,
   `development` included (a pre-1.0 hotfix: BUILT, its upload), and the first check counts from that time. Before
   any card or report that mentions `pre-release` or the default branch, ask: does it hold the notes or ask a person
   which branch? Then it is wrong: post now and report where it landed. A branch move is the person's own act, never
   a precondition for the notes or a question (lesson:
   [the notes never wait on a Steam branch](../lessons/a-release-is-done-when-its-notes-are-posted.md#the-notes-never-wait-on-a-steam-branch-w2431-w2440)). Posted
   once, as Max in #dev-patch-notes
   (`ci-release` section 3, `post_as_max` from any machine), with the wording from step 2, linted (step 2b). The release is not done without the
   message link; a failed post is reported as an open step with FFBox's reason (lesson:
   [a release is done when its notes are posted](../lessons/a-release-is-done-when-its-notes-are-posted.md)).

A release that is asked for is pre-approved, except the go-live moment of major new content (item
1b). Don't send the requester the other steps as questions: do them, and report what you found with each number labelled measured or sourced.
