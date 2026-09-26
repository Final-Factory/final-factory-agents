---
name: ci-release
description: Cut a release through the ffbox build server — bump the version (FFVersion.cs + bundleVersion), commit and push it, then follow CI as it builds Windows and Mac, main and demo, checks them and, once the tests pass, uploads each app to Steam (main first). A DEVELOP release is the multiplayer closed-beta build — develop's players have multiplayer (FF_ENABLE_MULTIPLAYER_BUILD in ProjectSettings, #613/#614) and ffbox sets the main app live on the `multiplayer-closed-beta` branch by itself (ffbox a7809f9e1). A MASTER release is the public release — uploaded with nothing set live, promoted by hand. Use when Ben or Lothsahn asks for either in any words — "push a new beta build", "deploy to the MP beta", "a multiplayer build for the testers", "cut a develop release" (develop); "cut a release on master", "a public release" (master). Never start it on your own initiative or as a side step of other work. The manual M5 procedure (mp-beta-deploy) is only a fallback for when ffbox is down or for a special build.
---

# Trigger a CI release on master or develop

> **Which branch is which (Lothsahn, 2026-09-26):**
> - **develop = the multiplayer closed beta.** develop's players ship multiplayer
>   (`FF_ENABLE_MULTIPLAYER_BUILD` is in develop's `ProjectSettings.asset` Standalone defines, #614;
>   the Build menu no longer strips it, #613/#614), and ffbox sets a develop release's **main** app
>   live on the password-protected **`multiplayer-closed-beta`** branch as it uploads
>   (`release_lane.SETLIVE`, ffbox `a7809f9e1`). The demo app sets nothing live. So "a new beta
>   build", "a multiplayer build for the testers" or "the closed beta" is a develop release here.
> - **master = the public release.** Uploaded with nothing set live; Lothsahn or Ben promotes it to
>   the default branch by hand. master has multiplayer once develop's ProjectSettings are merged up.
>
> The manual M5 procedure, `mp-beta-deploy`, is now only a fallback: ffbox down, or a special build
> that must not come from develop's tip.

**Only when Ben or Lothsahn asks** (plain English is enough). A release uploads builds other people
download, so never start one yourself; if you think one is due, say so and wait.

## How it works (so you can tell what went wrong)

**The version bump IS the release.** A commit on master or develop whose `FFVersion.cs` version differs
from its first parent's is built; nothing else is. `main.yml`'s `versionBump` job (ubuntu-latest) checks
that first; on any other push the `Release` and `Release demo` jobs show as **skipped**, which is
normal. On a bump they run on the ffbox runners **beside the tests, not after them**:
`Release (win64, main)` and `Release (osx, main)` start as soon as `versionBump` says yes, and
`Release demo (win64, demo)` and `Release demo (osx, demo)` start once both main jobs have finished.
`Warm release cache` is skipped on a bump, because the main release builds write the target caches.
Each release job asks the ffbox host, and the host grants only when:
- GitHub confirms the job is a push of that branch at that exact commit,
- the commit is on the branch's first-parent history and changes the version,
- and that version has not been built on that branch before.

Each granted job builds one player with `Editor.ReleaseBuild`, starting warm from CI's per-target
cache (about 5–15 min for a main player). The host then checks it: the exe, the entity scenes, the
Addressables, no symbols left in, the version, and **no asset import error**. It files the symbols by
version.

**Each app uploads on its own, and only after the tests pass.** Once an app's two players (Windows and
Mac) are GOOD, the host waits until every `Test in …` job of the same CI run has succeeded, then
uploads that app to Steam as `Lothsahn_FFBox`, exactly as Build and Upload All did: `desc` is the
version and **nothing is set live, except a develop release's main app, which goes live on
`multiplayer-closed-beta`** (the notice says "set live on multiplayer-closed-beta"). So main (app 1383150) goes up as soon as its players and the tests
are done, without waiting for the demo, and the demo (app 2387320) follows. If a test job fails, both
uploads are skipped with a notice; the players are still built and their symbols filed. Every other build
Lothsahn and Ben promote to Steam branches by hand. The host also posts notices to #agent-testing
(`release.channel`) and, once all four players are GOOD, opens a PR
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

**Do not run tests, open the editor, or read the git log to work out the bump.** The script below is
the whole of it, and a change to two version lines has nothing to test.

## 1. Start it: one command

The game repo's `scripts/trigger-ci-release.sh` makes the bump: the `FinalFactoryVersion` line in
`FFVersion.cs` and `bundleVersion` in `ProjectSettings.asset`, committed alone with the version as the
message. The Unity editor's **Build → Trigger CI Release** runs the same script.

**Where you can push** (a session on a dev machine, or on the ffbox host itself; `gh auth status`),
from any FinalFactory clone, on any branch, with any uncommitted work. The script builds the commit
on origin's tip of the branch without touching your checkout, pushes it, and retries if the branch
moved:

```sh
scripts/trigger-ci-release.sh develop --dry-run    # shows the two-line bump, changes nothing
scripts/trigger-ci-release.sh develop              # bumps origin/develop's tip and pushes it
scripts/trigger-ci-release.sh master --version 0.22.0.0
```

**In an ffbox container** (a Discord or web turn on the build server), which cannot push to master
or develop:

```sh
scripts/trigger-ci-release.sh develop --commit-only
```

That commits the bump on a new branch `release-<version>` off `origin/develop` and checks it out.
Then end your turn, leaving HEAD there. The harness skips the test run for a version-only change and
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

- **In #agent-testing:** notices for "building", each player GOOD or FAILED (with the failed check), and
  one "<app> uploaded to Steam … BuildID …" per app, main first (read with `ffdiscord`, see the
  ff-discord `discord-cli` skill).
- **On the ffbox host:** the ledger `~/ffbox-state/builds/<branch>/<version>/release.json` holds every
  state: `workers`, the CI `run` whose tests gate the upload, `uploads.main` / `uploads.demo` with
  their BuildIDs, and the regenerated-files PR.

Report main as soon as it is uploaded, then the demo when it follows: the version, the commit, the
four results, the two BuildIDs (main app 1383150, demo app 2387320), and the regenerated-files PR if
there is one. For develop, confirm the main
notice says "set live on multiplayer-closed-beta" (and `uploads.main.setlive` in the ledger); for
master, remind them that nothing is live and they promote the build on the partner site.

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

A failed worker does not retry by itself. After fixing the cause, bump again: each version is built once.
