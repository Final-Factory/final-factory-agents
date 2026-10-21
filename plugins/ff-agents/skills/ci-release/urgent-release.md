# The urgent release lane: BEAST (else LothDesktop) builds and uploads, FFBox skips

**When:** only when Ben or lothsahn asks for a **quick** or **urgent** release (or build) in their own words. lothsahn,
2026-10-20 (w1639): "Release builds should be handed by ffbox. We should update the version and just let ffbox build it.
But that can take up to 90m because ffbox is slow. If we need an urgent build, we should be able to ask beast or
Lothdesktop to build it for us. For that, we need to kick everyone else off the box (or at least have them pause) and then
do the release directly on the box and upload to steam. We need to make sure when that happens that ffbox doesn't see the
version update and do it's own release ... Then Ben and I can ask for a release (ffbox) or a quick or urgent release
(beast, if offline, LothDesktop)". Any other release is `SKILL.md` section 1 (FFBox). Design and evidence: the game repo's
`Documentation/Release-Lanes.md`.

Everything else in `SKILL.md` holds: the preconditions (section 0: no red master batch naming a culprit, saves load, the content go-live
question), the notes first (0.5), "Build R" in the notes, and **the patch-notes post as Max in #dev-patch-notes once live
is the last step** (section 3), then the first check (4).

## 0. One card first: A or B (w1656)

lothsahn, 2026-10-21: "Update your rules to ask about B when someone asks for an urgent release. That way we can choose to
immediately build off an older commit". Before the bump, unless the person already said which, run this in the game repo:

```sh
python scripts/release/last_green.py
```

It names the newest fully green master commit and the merges since it. Fully green means its `master-batch.yml` run
passed (the whole EditMode suite and the smoke PlayMode test), or it is a release bump whose own push run passed `Test in
editmode` (the whole EditMode suite; the batch skips bumps since w1658). It then prints the card. Bring it as ONE
question with `waiting_on_person` to the person who asked (their orchestrator asks it as given), with the real sha and
count, B recommended:

- "Build now from the last fully green commit `<sha>` (B: skips the N merges since it)"
- "Bump on master's tip (A: ships N merges that only had gate tests)"

When the script says **B is not offered**, go with A and no card: master's tip is itself green (A and B are the same
build), or the green commit is older than master's latest release (B would take that release's changes back out of
players' hands). The game repo's `Documentation/Release-Lanes.md`, "A or B", has the design.

## 1. The computer: BEAST, else LothDesktop when BEAST is offline

`list_machines` says which is online. The request runs at priority **urgent** (its bench tickets go first). Your sandbox
must be on that computer; if it is not, ask the dispatcher to place the request there (it clears a full BEAST with
`build_plan coming` and the request's work_id first).

**The build runs in that computer's slot1** (w1668; lothsahn: "Let's make sure that urgent builds always get scheduled
in slot1 on whatever machine they run in so that it uses caches as warm as possible"). The lane builds the checkout it
runs from, and a Library that never built Mac or Linux compiles every shader for it (1.0.0.3 in a cold slot3: about an
hour more). FF Factory keeps slot1's caches on BEAST and LothDesktop (no trim, no reseed), and `build_plan start` moves
you there (step 3). Its library line (`preflight`, every run) names the targets slot1 never built: then, outside an
urgent release, a worker in slot1 runs `python scripts/release/urgent_release.py warm` once (it builds only the cold
targets, main, uploads nothing, and waits its turn in the bench queue).

Once per computer, before its first urgent release:

```sh
python scripts/release/urgent_release.py preflight      # READY, or what is MISSING
python scripts/release/urgent_release.py steam-install --account <name>  # steamcmd and its config in <FF_WORKER_ROOT>/steam
```

`--account` is the build account FFBox's config names (`release.steam.account`); the first install needs it, then
`config.json` keeps it. No account is written in code (lothsahn: "It should not be hardcoded in the code").

`preflight` checks the computer is an urgent-lane one, that its Unity has Windows, Mac and Linux build support
(`FF_RELEASE_UNITY` names another Unity; BEAST uses `F:\ffw\tools\unity-release\6000.3.19f1\Editor\Unity.exe`, a copy
with the Linux module, w1639), 60 GB free, steamcmd, and the Steam login. **The Steam login needs no person**
(lothsahn, w1639: "we should put the secret in the secrets file for ffbox and have it authenticate rather than a manual
setup step"). FFBox's `ffsteam.py` logs the build account in by itself from `FFSTEAM_PASSWORD`, which FF Factory's
vault gives the workers of BEAST and LothDesktop as environment; `preflight` says `automatic Steam login:
FFSTEAM_PASSWORD from the vault`. `FFSTEAM_GUARD_SECRET` (an authenticator's `shared_secret`) is optional: the account
has no authenticator (lothsahn: "Let's assume no authenticator for now. If we have one we'll deal with that next.").
Never print, echo or log either; check them by name only.
- `preflight` says the run has no `FFSTEAM_PASSWORD`, or `steam login:` fails with exit 3 (ffsteam says why, and
  `auto-login.json` in the steam home keeps it): the step is a vault owner's. Bring it with `waiting_on_person`, asking
  them to add or fix the vault entry (kind env, `FFSTEAM_PASSWORD`, workers on beast and lothdesktop, shared with any
  run). Never ask them for the value, and never ask a person to type a login in a terminal.
- The run says `STOPPED: Steam asked for a Steam Guard code`: the password alone cannot pass the account's Steam
  Guard. Nothing was uploaded; report it to lothsahn as the blocker (how the account handles Steam Guard is his call),
  and do not retry.
- The run says `STOPPED: Steam emailed a Steam Guard code`: the build account has **email** Steam Guard (measured on
  BEAST, w1639), the password was right, and this computer is new to the account. Once per computer: ask lothsahn with
  `waiting_on_person` for the code from the newest such email, then run `preflight` once with `FFSTEAM_GUARD_CODE` set
  to it in that one command's environment (never echoed, never in a file or commit). It logs in past the hour's wait
  and authorises the computer; later runs need the password alone. Do not run `preflight` again before the code
  arrives: each try emails a new code.
- `steam-login` is only the fallback for a computer that cannot have the vault's values.

## 2. The bump, with the claim

```sh
scripts/trigger-ci-release.sh master --urgent beast --request wNNN --notes "$TMPDIR/release-notes-<v>.md"   # A; lothdesktop when BEAST is offline
scripts/trigger-ci-release.sh master --urgent beast --from green --request wNNN --notes "$TMPDIR/release-notes-<v>.md"   # B
```

**Draft the notes in `$TMPDIR`, not the project's `Temp/`, on this lane** (w1700, 1.0.0.8): the worker stops its
sandbox's editor before the build, and Unity deletes the project's `Temp/` when the editor exits, so a draft in
`Temp/release-notes-<v>.md` was gone when the trigger ran and had to be recovered from the transcript.

**B** makes the bump commit on the green commit, not on master's tip, and the claim names it (`"from"`). Its pull request
`release/<v>` merges into master as any bump does: master's version becomes the released one, the merges since the green
commit stay on master for the next release, and FFBox declines the merge by the claim. The lane builds **the branch's
head** (the green commit plus the bump), so start it at once, before the merge (section 3, step 1 with the head's sha).
It uploads only once the merge is there and is what it built. Its test gates are the green commit's own run AND the
merge's push run, as for A (w1705, lothsahn: "we only release if green"): a red push run ships nothing. Never merge master into that branch (`ff-pr push` does: merge the bump PR with `gh pr merge`): the lane then
refuses it.

The bump commit also carries `cicd/release-lane.json` claiming the version for that computer, so the claim reaches
master in the same merge as the version. FFBox's release lane reads it with ffbox `scripts/release_claim.py` and
declines every Release job of that run (its log: `release: declined: master <v> at <sha> is claimed by the urgent release
lane on beast for wNNN`); it builds and uploads nothing for that version. Merge the bump PR normally on green (no
`[skip ci]`: the push run's tests are a gate, as on FFBox). The bump PR's own check passes in about 2 minutes with no
editor (the claim counts as a bump file, w1705): the push run's whole suite is the one test run, and it runs beside the
build. lothsahn: "we should get the build going on Beast or LothDesktop in parallel to the test run.  We shouldn't wait
for the test run.  But we also need to make sure the master full test run goes and we only release if green". Read what master took since the bump before you merge
(`SKILL.md` section 1).

## 3. Clear the computer, build, check, upload, resume

Right after the merge:

(For B, right after `trigger-ci-release.sh` pushed `release/<v>`, with that branch's head instead of the bump commit.)

1. Put your sandbox on the bump commit: `git fetch origin && git branch urgent/<v> <bump sha>`, then
   `mcp__machine__switch_branch` to `urgent/<v>` (stop your editor first).
2. `build_plan coming` (release: true, minutes 0, what "the <v> urgent release"), then `build_plan start`. **The release
   build waits for no one** (w1656; lothsahn, after 1.0.0.3 waited 12 minutes for a worker to pause and 15 more behind
   its compile and test run: "i said it was urgent. How do we never let this happen again? It was supposed to kick work
   off the machine"). `start` says go at once. FF Factory moves the workers there between turns, asks the ones mid-turn
   to pause, and stops the editors of the workers it paused, so their compiles and test runs end and run again after
   `done`. Your bench tickets count as urgent, and the lane's Unity runs **pre-empt** the bench queue: whatever holds it
   (a batch run, a timed leg) stops cleanly and runs again after `done`. One "Not yet" is obeyed: **`Not yet (w1668)`**
   means you are not in slot1. Commit and push, then end your turn with no check-in: FF Factory empties slot1 (its
   workers go to other sandboxes there, on their branches) and moves you in on your branch, then resumes you there,
   usually within two minutes. Pin the new editor instance it names, and `build_plan start` again. Declaring `coming`
   early lets this happen at a turn you end anyway (waiting for the bump's CI). If slot1 cannot be emptied within 10
   minutes you are told to build where you are. Never wait on any other "Not yet": if a worker has not paused, build
   anyway. A **Live view** stays open: its worker is told to start no compile, test or build until you are
   done. Never close or move a Live view's editor yourself.
3. Run the lane (about an hour of Unity at first, less once each target's Library is warm; measured in w1639's proof):

   ```sh
   python scripts/release/urgent_release.py run --version <v> --unity "<Unity with Linux support>" \
       --out "$TMPDIR/urgent-<v>" > "$TMPDIR/urgent-<v>.log" 2>&1 &
   ```

   It refuses anything not claimed for this computer (FFBox builds those), then builds Windows, Mac and Linux, main then
   demo, with `.github/scripts/build-release.sh` itself (one Unity slot and one exclusive bench ticket per target), checks
   each player with FFBox's `ffrelease-check.py`, waits until every `Test in` job of the push run passed and FFBox
   declined every Release job, uploads each app with FFBox's `ffsteam.py` as the build account (main live on
   **development** only, never pre-release or default; the demo nowhere), opens the regenerated-files PR, and writes
   `urgent-release.json` (every phase's start, end and seconds; the BuildIDs) in its run folder. Exit 3: it could not
   log in to Steam by itself (section 1). Use `--preview` for a first run on a new computer (manifests, no upload).
   It takes 60+ minutes. **Follow it every 2 to 3 minutes, never with a 20 or 30 minute `wake_me`** (lothsahn, w1656:
   "Please update the urgent build instructions to have the worker check back every couple minutes to see if the build
   is done. It's waiting for almost 20 minutes, which seems far too long."):

   ```sh
   python scripts/release/urgent_release.py wait --out "$TMPDIR/urgent-<v>" --log "$TMPDIR/urgent-<v>.log" --minutes 3
   ```

   It returns the moment a phase starts or ends, or the log says REFUSED, STOPPED, a failure or done, with one line of
   every phase (exit 0), and after 3 minutes with nothing new (exit 1). Act on it, then call it again (a Bash call with
   timeout 240000) until the run is done. The run's own first line names this command.
4. **`build_plan done` at once**, done or failed: the paused work resumes.
5. Merge the regenerated-files PR on green, like FFBox's.
6. **The symbols into FFBox's store, before the release counts as done.** lothsahn (w1639): "Please make sure that if
   beast does a build that the symbols get uploaded to ffbox in the normal place so it can diagnose crashes and
   desyncs". The run's last phase (`symbols`) packed one archive per app and platform in `<out>/symbols/` and printed
   them. `publish_attachment` each archive it lists, then `file_ffbox_symbols` with the version and one entry per build
   (`{app, platform, attachment}`; main's and the demo's archive is usually the same file, named in both entries). It
   answers within 40 s; call it again with just the version until every build says `filed` (minutes). Then check
   `list_ffbox_files what "symbols" version "<v>"`: the version is listed with `master@<commit>` and `urgent/beast@<commit>`.
   FFBox refuses a version no urgent bump claimed and never files over its own symbols. If the run failed before
   packing, `urgent_release.py symbols --version <v> --out <the run folder>` packs them again. Never copy files to FFBox
   any other way: it has no other way in, by design ("We don't want a new public endpoint on ffbox").

## 4. Live, notes, first check

`python scripts/release-status.py <v>` prints `Lane: URGENT` and LANDED on development with the BuildID. Then post the
notes as Max (`SKILL.md` section 3: post_as_max, channel dev_patch_notes, key the version, from the committed
`cicd/release-notes/<v>.md`, skip_lines 2) and do the first check (section 4). The report gives the
`urgent-release.json` timings, the BuildIDs, the notes link, the symbols (`file_ffbox_symbols`' last answer: each build
filed, the bytes and the rate), and FFBox's decline (each Release job's build step
`skipped` in the run; `gh run view <run> --json jobs`).

## When it fails

- **Refused before building** (exit 2): it says why. Unclaimed or claimed for another computer means FFBox (or that
  computer) owns the version.
- **A player NOT GOOD, a test failed, or FFBox built it too**: nothing is uploaded. Nobody releases that version now:
  bump the next one, normally (FFBox) or urgent again. Versions are cheap; never re-tag or reuse one.
- **steamcmd failed mid-upload** (one Steam session per account, and FFBox uses the same account): run again with
  `--skip-build --out <the same folder>`; it re-checks and uploads what is built.
