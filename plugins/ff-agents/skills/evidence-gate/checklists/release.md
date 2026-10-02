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
3. **Saves still load.** The hard rule, as `ci-release` section 0 has it: the golden-fixture and
   layout tests pass in the release run, and a layout change has its upgrade step.
4. **Write what you expect:** which players build, which branch goes live with which app, and the
   test counts you expect to see.

## After it is live: the first check, within an hour

5. **It is the build you meant.** The BuildID on `multiplayer-beta` (a develop release) is the new
   one, per the upload notice and the ledger. `ci-release` section 2 has the commands.
6. **Players are not worse off than on the previous build.** Read, by version and by platform
   (Windows, Mac): the crash and desync reports players' games uploaded for the new version
   (FFBox's intake holds them; an orchestrator sees them with `ffbox_activity`), and new threads
   in the bug channels that name it (`ffdiscord read`). Reading is all you do there; FFBox owns
   those channels.
7. **Stop and report** when a save does not load, a platform is missing, or reports for the new
   version are clearly above the previous one's. Give the evidence and the previous BuildID.
   Rolling back or promoting a branch is the owner's call; never move a Steam branch by hand.
8. **Patch notes go out once it is confirmed live** (`ci-release` section 3), with the wording
   from step 2.

A release that is asked for is pre-approved. Don't send the requester these steps as questions:
do them, and report what you found with each number labelled measured or sourced.
