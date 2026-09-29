---
name: ci-release
description: Cut a release through the ffbox build server — bump the version (FFVersion.cs + bundleVersion), commit and push it, then follow CI as it builds Windows and Mac, main and demo, checks them and, once the tests pass, uploads each app to Steam (main first), writing the release notes first so they ride in the bump (cicd/release-notes/<version>.md: the Steam build description ffbox uploads with, and the player-facing post), then once it is live posting those notes as Max in #dev-patch-notes. A DEVELOP release is the multiplayer closed-beta build — develop's players have multiplayer (FF_ENABLE_MULTIPLAYER_BUILD in ProjectSettings, #613/#614) and ffbox sets the main app live on the `multiplayer-beta` branch by itself (ffbox f9174b61d; the closed beta was retired 2026-09-28). A MASTER release is the public release — uploaded with nothing set live, promoted by hand. Use when Ben or Lothsahn asks for either in any words — "push a new beta build", "deploy to the MP beta", "a multiplayer build for the testers", "cut a develop release" (develop); "cut a release on master", "a public release" (master). Never start it on your own initiative or as a side step of other work. ffbox CI is THE way to build releases and is expected to work; the manual M5 procedure (mp-beta-deploy) is a last resort, only when ffbox CI is actually down and only with Ben's OK.
---

# Trigger a CI release on master or develop

> **Which branch is which (Lothsahn, 2026-09-26):**
> - **develop = the multiplayer closed beta.** develop's players ship multiplayer
>   (`FF_ENABLE_MULTIPLAYER_BUILD` is in develop's `ProjectSettings.asset` Standalone defines, #614;
>   the Build menu no longer strips it, #613/#614), and ffbox sets a develop release's **main** app
>   live on **`multiplayer-beta`** as it uploads (`release_lane.SETLIVE`). The password-protected
>   `multiplayer-closed-beta` is retired (owner, 2026-09-28, ffbox `f9174b61d`): ffbox no longer sets
>   it live and `ffsteam.py` refuses an upload asking for it (0.50.0.45 went live on
>   `multiplayer-beta` alone, BuildID 25587352). Nobody moves the branch by hand. The demo app sets
>   nothing live. So "a new beta build", "a multiplayer build for the testers" or "the closed beta"
>   is a develop release here.
> - **master = the public release.** Uploaded with nothing set live; Lothsahn or Ben promotes it to
>   the default branch by hand. master has multiplayer once develop's ProjectSettings are merged up.
>
> **ffbox CI is THE way to build releases, and it is expected to work** (Lothsahn, 2026-09-28). The
> manual M5 procedure, `mp-beta-deploy`, is a last-resort fallback: only when ffbox CI is actually
> down, and only with Ben's OK. A failed player is not "ffbox down": get the reason from the job log,
> report it, and fix it here (re-run the job or bump again); never switch to `mp-beta-deploy` on your own.
>
> History: the 0.50.0.36/.37/.39 Mac players failed with "Disk full" on the `ffghr-loth2400-*`
> runners (2026-09-27). Lothsahn fixed it in ffbox (the nightly cache rebuild, FinalFactory #651, and
> more); it is resolved, not a risk to watch for (0.50.0.42's Mac players built GOOD).

**Only when Ben or Lothsahn asks** (plain English is enough). A release uploads builds other people
download, so never start one yourself; if you think one is due, say so and wait.

## How it works (so you can tell what went wrong)

**The version bump IS the release.** A commit on master or develop whose `FFVersion.cs` version differs
from its first parent's is built; nothing else is. `main.yml`'s `versionBump` job (ubuntu-latest) checks
that first; on any other push the `Release` jobs show as **skipped**, which is normal. On a bump
they run on the ffbox runners **beside the tests, not after them**: `Release (win64)` and
`Release (osx)` start as soon as `versionBump` says yes. **Each job builds its target's main player,
hands it to the host, then builds the demo in the same workspace** (since 2026-09-28; before that
there were four jobs, `Release (win64, main)` … `Release demo (osx, demo)`). The demo reuses the
Burst code main just compiled, because demo mode is a scene flag, not a define. Each job asks the
ffbox host for both editions (`main,demo`), and the host grants each edition only when:
- GitHub confirms the job is a push of that branch at that exact commit,
- the commit is on the branch's first-parent history and changes the version,
- and that version has not been built on that branch before.

Each granted edition is one `Editor.ReleaseBuild` session. The job starts from the target cache the
nightly "Rebuild caches" workflow wrote (releases write no cache), so a main player pays Burst for
everything pushed since that night: about 10–20 min, more on a busy box or after a big day. The demo
after it should be much shorter. The host grants each edition on its own, so a re-run of a job whose
main player is already GOOD builds only the demo. The host then checks it: the exe, the entity scenes, the
Addressables, no symbols left in, the version, and **no asset import error**. It files the symbols by
version.

**Each app uploads on its own, and only after the tests pass.** Once an app's two players (Windows and
Mac) are GOOD, the host waits until every `Test in …` job of the same CI run has succeeded, then
uploads that app to Steam as `Lothsahn_FFBox`, exactly as Build and Upload All did: `desc` is the
version and **nothing is set live, except a develop release's main app, which goes live on
`multiplayer-beta`** (the notice: "main uploaded to Steam, set live on multiplayer-beta (BuildID
…)"). From `d46d438d5` to `f9174b61d` (2026-09-28) it also went live on `multiplayer-closed-beta`,
one BuildID per branch; releases up to 0.50.0.44 name both. So main (app 1383150) goes up as soon as its players and the tests
are done, without waiting for the demo, and the demo (app 2387320) follows. If a test job fails, both
uploads are skipped with a notice; the players are still built and their symbols filed. Every other build
Lothsahn and Ben promote to Steam branches by hand. The host also posts notices to #release-build-announce
(`release.channel`; 0.50.0.42's all landed there, none in #agent-testing) and, once all four players are GOOD, opens a PR
`ffbox/release-<version>-regenerated` for any tracked files the build regenerated (localization
harvest, font atlases).

Design and code: ffbox repo `design/ffbuild_release_design.txt`, `scripts/release_lane.py`,
`scripts/ffsteam.py`; README "Release players and the Steam upload"; config.md "release".

## 0. Preconditions

- Which branch: master or develop only, as asked. Never bump a feature branch: that is not a release.
- Which version: the RC (the fourth number) plus one, unless you were told otherwise (e.g. a minor
  bump `0.21.0.30` → `0.22.0.0`, which is `--version 0.22.0.0` below). Say the version before you push.
- Nothing already in flight for that branch: check that the latest version bump's release has finished
  (section 2) before starting another.
- **Tests: the release run's own `Test in editmode` job is the gate; run none yourself**
  (Lothsahn, 2026-09-28, replacing the local-precheck rule of 1.16.3). The bump push runs the full
  EditMode suite on ffbox beside the builds, and the host uploads nothing until every `Test in …`
  job of that run has succeeded (upload skipped otherwise, see the table below). Do not start a
  local `FFEditorTests` run or look for an earlier PR result before triggering. In the report,
  confirm that job ran and passed, with its counts from the check run "editmode Test Results:
  success <N> passed" (`gh run view <id> --json jobs`: conclusion `success`, several minutes long;
  0.50.0.45's ran 5541, 5520 passed, 0 failed). If it failed, report the failing tests; do not
  fall back to anything.

- **Saves from master's version and every beta since still load** (hard rule, project-memory
  `save-compatibility-hard-rule`; 0.50.0.45 shipped unable to load any 0.50.0.35..44 save).
  `Tests.Serialization.GoldenSaveFixtureTests` and `Tests.Serialization.SaveLayoutSnapshotTest` are
  EditMode tests, so the release run's gate runs them; name them as passed in the report. (CI runs
  EditMode only, `main.yml` `testMode: editmode`, so the PlayMode `SaveCompatibilityLiveLoadTest` is
  not a release precondition.) Before bumping, if `git diff <previous release>..HEAD` touches a
  `[Save]` struct, `SaveState` or an `ISerializableSystem` payload, find the matching `UpgradeStep`;
  if there is none, stop and say so. A step versioned at the release version runs for older saves
  and never again once the bump stamps saves with it (`UpgradeChain.Applicable`: `from <
  step.Version`). After a develop release, mint a golden fixture from a save that release writes
  when it starts a new layout generation, so the next beta is tested against it.

**Do not run tests for the bump commit itself.** The script below is the whole of it, and a
change to two version lines (plus its notes) has nothing to test beyond the HEAD it sits on.

## 0.5. Write the release notes first (they ride in the bump)

**Every release carries its notes** (Ben, 2026-09-28). Before triggering, write
`Temp/release-notes-<version>.md` in your checkout from `git log <previous release>..origin/<branch>`,
exactly as **`patch-notes.md`** beside this file says: line 1 is `steam_description: <short change
list>` (ffbox makes it the Steam build's description, `<version> (<sha9>): <that line>`), line 2 is
blank, and the rest is the player-facing #dev-patch-notes post. Then pass it to the script with
`--notes`, which commits it with the bump as `cicd/release-notes/<version>.md`. The script refuses a
file without the `steam_description:` line.

## 1. Start it: one command

The game repo's `scripts/trigger-ci-release.sh` makes the bump: the `FinalFactoryVersion` line in
`FFVersion.cs` and `bundleVersion` in `ProjectSettings.asset`, committed alone with the version as the
message. With `--notes FILE` it adds that file as `cicd/release-notes/<version>.md` in the same
commit. The Unity editor's **Build → Trigger CI Release** runs the same script (without notes, so its
Steam description is only the version: prefer the command line).

**Where you can push** (a session on a dev machine, or on the ffbox host itself; `gh auth status`),
from any FinalFactory clone, on any branch, with any uncommitted work. The script builds the commit
on origin's tip of the branch without touching your checkout, pushes it, and retries if the branch
moved:

```sh
scripts/trigger-ci-release.sh develop --dry-run --notes Temp/release-notes-0.50.0.43.md   # shows it, changes nothing
scripts/trigger-ci-release.sh develop --notes Temp/release-notes-0.50.0.43.md             # bumps origin/develop's tip and pushes it
scripts/trigger-ci-release.sh master --version 0.22.0.0 --notes Temp/release-notes-0.22.0.0.md
```

**In an ffbox container** (a Discord or web turn on the build server), which cannot push to master
or develop:

```sh
scripts/trigger-ci-release.sh develop --commit-only --notes Temp/release-notes-<version>.md
```

That commits the bump on a new branch `release-<version>` off `origin/develop` and checks it out.
Then end your turn, leaving HEAD there. The harness skips the test run for a version-only change (the
notes file counts as part of it once ffbox PR #3 is merged; until then it runs the suite) and
opens a pull request against develop; **merging that PR is what starts the release**, so say so in
your reply with the version. Do not run `ffverify` for it.

If the checkout you are in predates the script, run the branch's copy:
`git show origin/develop:scripts/trigger-ci-release.sh | bash -s -- develop` (same arguments).

**Never use Build → Build and Upload All for this.** It builds and uploads on your machine and commits
`cicd/depot_build_*.vdf`. The host treats that mark as "already uploaded by hand", so it builds that
version for its symbols but does not upload it.

## 2. Follow it and report

```sh
gh run list -R Final-Factory/FinalFactory -b <branch> -L 3        # the run for your commit
gh run view <run id> -R Final-Factory/FinalFactory --json jobs -q '.jobs[] | "\(.name): \(.status) \(.conclusion)"'
```

- **In #release-build-announce:** notices for "building", each player GOOD or FAILED (with the failed check), and
  one "<app> uploaded to Steam … BuildID …" per app, main first (read with `ffdiscord read '#release-build-announce' --limit 10`, see
  the ff-discord `discord-cli` skill). A player with no GOOD/FAILED notice while its CI job shows
  success was never granted: see the "host did not answer" row below.
- **On the ffbox host:** the ledger `~/ffbox-state/builds/<branch>/<version>/release.json` holds every
  state: `workers`, the CI `run` whose tests gate the upload, `uploads.main` / `uploads.demo` with
  their BuildIDs, and the regenerated-files PR.

Report main as soon as it is uploaded, then the demo when it follows: the version, the commit, the
release run's `Test in editmode` result (ran, passed, its counts), the
four results, the two BuildIDs (main app 1383150, demo app 2387320), and the regenerated-files PR if
there is one. For develop, **verify `multiplayer-beta` got the new build**: the main notice says "set
live on multiplayer-beta (BuildID …)", and the ledger's `uploads.main.setlive` lists it with its
BuildID in `uploads.main.live_builds`. Report that BuildID. No closed-beta BuildID is expected any
more (retired, `f9174b61d`). If no branch is named, report that as an ffbox problem for its owner;
**never tell Ben to move a branch by hand**. For master,
remind them that nothing is live and they promote the build on the partner site.

## 3. Patch notes, once it is live

**Every release ends with patch notes** (Ben, 2026-09-28): once the build is confirmed live, post the
body of the release's `cicd/release-notes/<version>.md` (everything after its first two lines) as Max
in #dev-patch-notes (channel `1072387196927094845`), never with @everyone. Check the main upload
notice's desc too if you can see it (the ledger's `desc`). The procedure, the exact format with a
template, and the 403 rule are in **`patch-notes.md`** beside this file; follow it as written. Put the
message link in the release report. A release bumped without notes (the Build menu) still gets them:
write them from the commits then, and add the file to develop afterwards for the record.

## When it goes wrong

The host's reason for a declined or failed job is in the job log ("ask the host whether this push is a
release"), in `release.decided`, and in the ffbox journal (`journalctl -u ffwatch | grep release:`).

| What you see | Meaning, and what to do |
|---|---|
| declined: `release.enabled is false` | Releases are switched off in `~/.config/ffbox/config.json` on the ffbox host. Ask; do not flip it yourself. |
| `Release …` jobs skipped | `versionBump` saw no version change in the pushed commit. Normal for an ordinary push; for a bump, check that the pushed head IS the bump commit. |
| upload skipped: `the tests did not pass: …` | A `Test in …` job of the release's run failed. The players were built but not uploaded. Fix the test, then bump again. |
| upload waiting, players GOOD | The run's tests have not finished yet; the host asks GitHub once a minute. Normal. |
| declined: `does not change the version` | The pushed commit is not a bump. Bump and push again. |
| declined: `not on <branch>'s first-parent history` | The bump arrived only through a merge's second parent. Bump directly on the branch. |
| declined: `already built at <sha>` / `already built` | That version exists already. Bump again; a version is built once. |
| declined: `job identity not confirmed` | The host could not confirm the job with GitHub (the GitHub App needs Actions:Read and Contents:Read). Tell the ffbox owner. |
| a worker FAILED: `asset import error` | A Linux editor cannot import something (e.g. a video with transcoding on). Fix the asset settings, then bump again. |
| a worker FAILED: an AgentKit error | The host has no copy of the pinned kit (`/opt/ffcache/agentkit/<v>`; `scripts/agentkit.py ensure`). Tell the ffbox owner. |
| upload FAILED: `Steam login is gone` | On the ffbox host, a person runs `scripts/ffsteam.py login` (password + Steam Guard). |
| upload skipped: `uploaded it by hand` | The bump commit also changed `cicd/depot_build_*.vdf` (Build and Upload All). Expected. |
| upload skipped: `release.upload is off` / `no release.steam.account` | Host configuration. Ask. |
| a `Release …` job is green after about 10 minutes with no build step run and no GOOD/FAILED notice, and its log ends `the host did not answer in 600s; the checkout will likely fail` | The host never answered the job's mirror request, so the job skipped its build and still passed (0.50.0.42 win64-main, 2026-09-28). The version is NOT used up for that player. Once the whole run has finished, re-run only that job: `gh run rerun <run id> -R Final-Factory/FinalFactory --job <job id>`. The host granted the re-run, built it GOOD, and uploaded main. A re-run is granted only the editions not already built, so it never rebuilds a GOOD player. Tell the ffbox owner it happened. |

A failed worker does not retry by itself. After fixing the cause, bump again: each version is built once.
