---
name: ci-release
description: Cut a release through CI on the ffbox build server — write the release notes, bump the version (FFVersion.cs + bundleVersion) and push, follow CI through the Windows/Mac main+demo builds, tests and Steam uploads, then post the patch notes as Max in #dev-patch-notes. A requested release is done only when it is live on its Steam branch AND its notes are posted. ffbox sets a develop release's main app live on `development` and a master release's on `pre-release`, automatically; Ben or Lothsahn move the default branch by hand. `scripts/release-status.py` says where a release is. Use when Ben or Lothsahn asks for either in any words ("push a new dev build", "a build for the testers", "cut a release on master"). Never start it on your own initiative or as a side step of other work.
---

# Trigger a CI release on master or develop

> **WHERE A RELEASE LANDS (ffbox `scripts/release_lane.py`, `SETLIVE`).** Read it there, or run
> `python scripts/release-status.py [<version>]` in the game repo, which reads it from ffbox and the
> branches from Steam. Never from memory.
>
> ```python
> SETLIVE = {("develop", "main"): ("development",), ("master", "main"): ("pre-release",)}
> ```
>
> - **A develop release:** ffbox sets the **main** app live on **`development`**, automatically, as it
>   uploads.
> - **A master release:** ffbox sets the main app live on **`pre-release`**, automatically. master has
>   multiplayer since develop's ProjectSettings were merged up (`FF_ENABLE_MULTIPLAYER_BUILD`, #614).
> - **The default (public) branch** is moved by hand by Ben or Lothsahn on the partner site. An agent
>   never moves any Steam branch, and never proposes it while `release-status.py` says BUILDING or
>   WAITING.
> - **Never:** the demo app is set live nowhere; ffbox never sets the default branch.
> - **Timing, measured** (CI run start to the branch moving, 0.50.0.57 to .67, nine uploads): 22 to
>   78 min, median 36; after the Release jobs ended, -7 to +43 min (main uploads before the demo is
>   built). `release-status.py` calls it LATE only past 60 min after the Release jobs end.
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
version and **nothing is set live, except the main app on the branch `SETLIVE` names: `development`
for develop, `pre-release` for master** (the notice: "main uploaded to Steam, set live on
<branch> (BuildID …)"). So main (app 1383150) goes up as soon as its players and the tests
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
  **To players it is "Build R", its last number** (Ben, 2026-10-04, w395): 0.50.0.76 is Build 76 in
  the notes, the #dev-patch-notes post and the Steam description. The version stays four-part in
  everything else (the bump, file names, `release-status.py`, ffbox).
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
file without the `steam_description:` line, and (since w395) one that names a four-part version or
whose post does not call the release `Build <R>`.

**"Fixed" in the notes rests on something** (2026-10-02; `evidence-gate`, `checklists/release.md`). 0.50.0.64
told players two things were fixed that nobody had seen in a built game. For each player-visible fix, find
its pull request's `## Evidence`: looked at in a built player, write "Fixed"; otherwise say what changed, or
leave it out, and tell whoever asked for the release which fixes are unseen. `pr_evidence.py --audit
--since <date of the previous release>` (beside the `evidence-gate` skill) lists them.

## 1. Start it: one command

The game repo's `scripts/trigger-ci-release.sh` makes the bump: the `FinalFactoryVersion` line in
`FFVersion.cs`, the `ReleasedUtc` line under it (the bump's time in UTC, which the main menu shows
beside the version, w395) and `bundleVersion` in `ProjectSettings.asset`, committed alone with the
version as the message. With `--notes FILE` it adds that file as `cicd/release-notes/<version>.md` in the same
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
there is one. **Run `python scripts/release-status.py <version>`** (game repo): it prints the run,
the branch `SETLIVE` names for this release, every Steam branch's BuildID and time, a verdict and the
next step. Report the BuildID on that branch: **`development` for develop, `pre-release` for
master** (the notice: "set live on <branch> (BuildID …)"; the ledger's `uploads.main.setlive` and
`uploads.main.live_builds`). Then say plainly where it is not: a develop build reaches
`pre-release` only as a master release, and no build is on the default branch until Ben or Lothsahn
moves it there. BUILDING or WAITING is normal (measured 22-78 min from the
bump); only LATE is an ffbox problem for its owner. **Never move a Steam branch, never ask a worker to,
and never tell Ben a branch must be moved for the build to count**: report where it landed.

## 3. Patch notes: the required last step

**Every requested release ends with its patch notes posted in #dev-patch-notes** (Lothsahn,
2026-10-03: "any time a release is requested, you should always post the #dev-patch-notes after the
build is complete and uploaded"). A release is **done only when both** are true:

- [ ] **Live on its Steam branch**: `python scripts/release-status.py <version>` says LANDED, on
  `development` for a develop release or `pre-release` for a master release.
- [ ] **Notes posted once, as Max, in #dev-patch-notes** (channel `1072387196927094845`): the body of
  the release's `cicd/release-notes/<version>.md` (everything after its first two lines),
  player-facing, no internal ids, never with @everyone; the message link is in the release report.

The procedure, the exact format with a template, and the 403 rule are in **`patch-notes.md`** beside
this file; follow it as written. Check the main upload notice's desc too if you can see it (the
ledger's `desc`). A release bumped without notes (the Build menu) still gets them: write them from
the commits then, and add the file to develop afterwards for the record.

**Posting needs a machine with the ffdiscord config** (the `discord` section and bot token that the
ff-discord `discord-cli` skill reads; LothDesktop today). Check before the bump:
`ffdiscord read 1072387196927094845 --limit 1` must list the channel's last post. If this machine
cannot post, the release is **not done**: report "live on <branch> (BuildID …), patch notes NOT
posted: no ffdiscord config on <machine>", with the notes file's path, and leave the posting step
open for a machine that has it. Never finish a release report without one of the two: the message
link, or that open step.

## 4. The first check, within an hour of live

A release is not done at the upload notice (`evidence-gate`, `checklists/release.md`). Within an hour of
the build going live: confirm the BuildID on the branch is the new one, then read, by version and by
platform, the crash and desync reports players' games uploaded for it and any new bug threads that name
it. A save that does not load, a missing platform, or reports clearly above the previous build's: tell
whoever asked for the release at once, with the evidence and the previous BuildID. Use `wake_me` so the
check happens when it is due.

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
