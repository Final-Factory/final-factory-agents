# The urgent release lane: BEAST (else LothDesktop) builds and uploads, FFBox skips

**When:** only when Ben or lothsahn asks for a **quick** or **urgent** release (or build) in their own words. lothsahn,
2026-10-20 (w1639): "Release builds should be handed by ffbox. We should update the version and just let ffbox build it.
But that can take up to 90m because ffbox is slow. If we need an urgent build, we should be able to ask beast or
Lothdesktop to build it for us. For that, we need to kick everyone else off the box (or at least have them pause) and then
do the release directly on the box and upload to steam. We need to make sure when that happens that ffbox doesn't see the
version update and do it's own release ... Then Ben and I can ask for a release (ffbox) or a quick or urgent release
(beast, if offline, LothDesktop)". Any other release is `SKILL.md` section 1 (FFBox). Design and evidence: the game repo's
`Documentation/Release-Lanes.md`.

Everything else in `SKILL.md` holds: the preconditions (section 0: master batch green, saves load, the content go-live
question), the notes first (0.5), "Build R" in the notes, and **the patch-notes post as Max in #dev-patch-notes once live
is the last step** (section 3), then the first check (4).

## 1. The computer: BEAST, else LothDesktop when BEAST is offline

`list_machines` says which is online. The request runs at priority **urgent** (its bench tickets go first). Your sandbox
must be on that computer; if it is not, ask the dispatcher to place the request there (it clears a full BEAST with
`build_plan coming` and the request's work_id first).

Once per computer, before its first urgent release:

```sh
python scripts/release/urgent_release.py preflight      # READY, or what is MISSING
python scripts/release/urgent_release.py steam-install  # Valve's steamcmd and its config in <FF_WORKER_ROOT>/steam; no login
```

`preflight` checks the computer is an urgent-lane one, that its Unity has Windows, Mac and Linux build support
(`FF_RELEASE_UNITY` names another Unity; BEAST uses `F:\ffw\tools\unity-release\6000.3.19f1\Editor\Unity.exe`, a copy
with the Linux module, w1639), 60 GB free, steamcmd, and the build account's cached login. **The Steam login is a
person's step, once per computer**: `python scripts/release/urgent_release.py steam-login` in a terminal on that
computer, which runs FFBox's own `ffsteam.py login` and asks for the build account's password and its Steam Guard code.
Bring it with `waiting_on_person` (one question: "Have you run the Steam login on BEAST?"), never as a list of commands
for them to work out. No password is stored anywhere; nothing goes in the vault.

## 2. The bump, with the claim

```sh
scripts/trigger-ci-release.sh master --urgent beast --request wNNN --notes Temp/release-notes-<v>.md   # lothdesktop when BEAST is offline
```

The bump commit also carries `cicd/release-lane.json` claiming the version for that computer, so the claim reaches
master in the same merge as the version. FFBox's release lane reads it with ffbox `scripts/release_claim.py` and
declines every Release job of that run (its log: `release: declined: master <v> at <sha> is claimed by the urgent release
lane on beast for wNNN`); it builds and uploads nothing for that version. Merge the bump PR normally on green (no
`[skip ci]`: the push run's tests are a gate, as on FFBox). Read what master took since the bump before you merge
(`SKILL.md` section 1).

## 3. Clear the computer, build, check, upload, resume

Right after the merge:

1. Put your sandbox on the bump commit: `git fetch origin && git branch urgent/<v> <bump sha>`, then
   `mcp__machine__switch_branch` to `urgent/<v>` (stop your editor first).
2. `build_plan coming` (release: true, minutes 0, what "the <v> urgent release"), then `build_plan start`. FF Factory moves
   the workers there between turns, asks the ones mid-turn to finish their step and pause, and leaves a **Live view**
   open: its worker is told to start no compile, test or build until you are done. Never close or move a Live view's
   editor yourself.
3. Run the lane (about an hour of Unity at first, less once each target's Library is warm; measured in w1639's proof):

   ```sh
   python scripts/release/urgent_release.py run --version <v> --unity "<Unity with Linux support>"
   ```

   It refuses anything not claimed for this computer (FFBox builds those), then builds Windows, Mac and Linux, main then
   demo, with `.github/scripts/build-release.sh` itself (one Unity slot and one exclusive bench ticket per target), checks
   each player with FFBox's `ffrelease-check.py`, waits until every `Test in` job of the push run passed and FFBox
   declined every Release job, uploads each app with FFBox's `ffsteam.py` as the build account (main live on
   **development** only, never pre-release or default; the demo nowhere), opens the regenerated-files PR, and writes
   `urgent-release.json` (every phase's start, end and seconds; the BuildIDs) in its run folder. Exit 3: the Steam login
   is gone, a person runs `steam-login` again. Use `--preview` for a first run on a new computer (manifests, no upload).
   It takes 60+ minutes: run it in the background and `wake_me` within 30 minutes so your editor-free sandbox stays yours.
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
