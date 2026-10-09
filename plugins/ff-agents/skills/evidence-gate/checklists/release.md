# Releases: before the bump and after it is live

The mechanics are the `ci-release` skill and stay as they are: a release starts only when Ben or
Lothsahn asks, the release run's tests gate the upload, and the notes ride in the bump. This list
adds what a release rests on and the first check after it.

## Before the bump

1. **What is in it.** `git log <previous release>..origin/<branch>`, as for the notes.
2. **Every "fixed" in the notes rests on something.** For each player-visible fix, find its pull
   request's `## Evidence`. Looked at in a built player: write "Fixed". Otherwise say what changed
   ("Changed how riders are drawn on a moving station") or leave it out, and tell whoever asked
   for the release which fixes nobody has seen in a built game.
   `pr_evidence.py --audit --since <date of the previous release>` lists them.
   Read every PR's "Not verified:" line in the range: a native or platform call nobody ran on that
   platform goes to whoever asked for the release and into the notes (Build 88 crashed every Steam
   Deck at start-up from `SetInputActionManifestFilePath` under Proton, listed "Not verified" in
   #1249; fixed in #1261).
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
   <version>` (game repo) says LANDED, with the BuildID on `development` for a develop release or on
   `pre-release` for a master release (ffbox `release_lane.SETLIVE`, read by the script). Any
   other branch is moved by a person; never propose moving one while the script says BUILDING or
   WAITING (lesson: [a release lands where SETLIVE says](../lessons/a-release-lands-where-setlive-says.md)).
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
9. **Patch notes are posted once it is confirmed live**, once, as Max in #dev-patch-notes
   (`ci-release` section 3), with the wording from step 2. The release is not done without the
   message link; a machine with no ffdiscord config reports the post as an open step (lesson:
   [a release is done when its notes are posted](../lessons/a-release-is-done-when-its-notes-are-posted.md)).

A release that is asked for is pre-approved. Don't send the requester these steps as questions:
do them, and report what you found with each number labelled measured or sourced.
