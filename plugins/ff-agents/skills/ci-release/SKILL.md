---
name: ci-release
description: "Cut a release through CI on the ffbox build server — write the release notes, bump the version (FFVersion.cs + bundleVersion) and push, follow CI through the Windows/Mac main+demo builds, tests and Steam uploads, then post the patch notes as Max in #dev-patch-notes. A requested release is done only when it is live on its Steam branch AND its notes are posted; `scripts/release-status.py` says where a release is. Use when Ben or Lothsahn asks for a build in any words (\"push a new dev build\", \"a build for the testers\", \"cut a release\"). Two lanes (w1639): \"a release\" is FFBox's (this file); \"a quick release\" or \"an urgent release\" is built and uploaded by BEAST, else LothDesktop, while FFBox skips it (urgent-release.md beside it). Never start it on your own initiative or as a side step of other work."
---

# Trigger a CI release (a version bump merged into master)

> **TWO LANES (w1639; lothsahn, 2026-10-20: "Release builds should be handed by ffbox. We should update the version and
> just let ffbox build it. But that can take up to 90m because ffbox is slow. If we need an urgent build, we should be
> able to ask beast or Lothdesktop to build it for us ... Then Ben and I can ask for a release (ffbox) or a quick or urgent
> release (beast, if offline, LothDesktop)").**
>
> - **"A release"** (any words without "quick" or "urgent"): this file. FFBox builds, uploads and sets development live;
>   no FF Factory computer builds it, and an FF Factory worker takes no `build_plan` for it. After the merge, `wake_me` 40
>   minutes and end the turn (FFBox lands 22 to 78 minutes after the bump, median 36), so no sandbox waits on FFBox.
>   First the person picks **A or B** on the same card as an urgent release (w1656; lothsahn: "A normal release should
>   also provide the option of starting from the last fully green commit"): section 1, "A or B first".
> - **"A quick release" / "an urgent release"** from Ben or Lothsahn: **`urgent-release.md`** beside this file. The bump
>   carries `cicd/release-lane.json` (`trigger-ci-release.sh --urgent beast`), FFBox declines it, and BEAST (else
>   LothDesktop when BEAST is offline) builds it with FFBox's own scripts after FF Factory clears it, uploads it and sets
>   development live. Never pre-release or default. First the person picks **A or B** on one card from
>   `scripts/release/last_green.py` (B: build now from the last fully green commit; A: bump on master's tip), the build
>   waits for no one and runs in that computer's slot1, its Library kept warm (w1668: `build_plan start` moves the
>   worker there), and the worker follows it every 2 to 3 minutes (w1656; urgent-release.md sections 0, 1 and 3).
> - Both: the notes first, the patch-notes post as Max in #dev-patch-notes once live as the last step (section 3).

> **WHERE A RELEASE LANDS (ffbox `scripts/release_lane.py`, `SETLIVE`).** Read it there, or run
> `python scripts/release-status.py [<version>]` in the game repo, which reads it from ffbox and the
> branches from Steam. Never from memory.
>
> ```python
> SETLIVE = {("master", "main"): ("development",)}
> RETIRED_BRANCHES = ("develop",)
> ```
>
> (ffbox commit 8fbb8d5, 2026-10-12, w1137: Ben, "i want to get off develop as a branch and do
> everything off master ... keep development steam branch at the tip of master until we are ready to
> release a batch of updates into main"; Lothsahn, "Let's just have steam development branch track
> master and have pre-release and default be manual tags".)
>
> - **A version bump merged into master IS a dev build:** ffbox builds it and sets the **main** app live
>   on **`development`**, automatically, as it uploads. `development` tracks the tip of master.
> - **develop is retired** (locked read-only on GitHub). A bump on develop is declined and builds
>   nothing.
> - **`pre-release` and the default (public) branch are set by nothing.** A release to players is Ben
>   or Lothsahn moving `pre-release` or the default by hand on the partner site. An agent never sets,
>   moves or plans a Steam branch, and never proposes it while `release-status.py` says BUILDING or
>   WAITING.
> - **Never:** the demo app is set live nowhere; ffbox never sets `pre-release` or the default branch.
> - **pre-1.0 is the production hotfix line until 1.0 ships** (w1436, Ben 2026-10-17: "any bug fixes that are
>   essential will be cherry picked to the pre 1.0 branch in the mean time for hot fixes"). A bump merged into
>   `pre-1.0` (0.50.0.R) builds and uploads both apps and sets NOTHING live (`UPLOAD_ONLY_BRANCHES`); master is
>   the 1.0 line (1.0.0.R, every 1.0 toggle on by default), its first bump after the cut 1.0.0.0. Fixes land on
>   master first, then a cherry-pick PR into pre-1.0. The whole route, numbers and notes: `pre-1.0-hotfix.md`
>   beside this file.
> - **Timing, measured** (CI run start to the branch moving, 0.50.0.57 to .67, nine uploads): 22 to
>   78 min, median 36; after the Release jobs ended, -7 to +43 min (main uploads before the demo is
>   built). `release-status.py` calls it LATE only past 60 min after the Release jobs end.
>
> **ffbox CI is THE way to build releases, and it is expected to work** (Lothsahn, 2026-09-28). The
> manual M5 procedure, `mp-beta-deploy`, is a last-resort fallback: only when ffbox CI is actually
> down, and only with Ben's OK. A failed player is not "ffbox down": get the reason from the job log,
> report it, and fix it here (re-run the job or bump again); never switch to `mp-beta-deploy` on your own.
>
> **FFBOX BUILDS AGAIN; THE M5 MANUAL BUILD IS HISTORY** (lothsahn, 2026-10-20, w1639: "Release builds should be
> handed by ffbox. We should update the version and just let ffbox build it"). That is the "FFBox builds again" that
> Ben's w930 rule waited for (Ben, 2026-10-10: "for the next build, please just do the process on my m5 ... ffbox is
> having issues with build speed so we are going to manually use my m5 for builds for a couple days"). A dev build is
> now a normal bump (section 1), and an urgent one is `urgent-release.md`. `m5-manual-build.md` stays for the record
> (Builds 97 and 99) and for a person who asks for an m5 build by name; `mp-beta-deploy` stays the last resort when
> FFBox CI is down and Ben has OK'd it.
>
> History: the 0.50.0.36/.37/.39 Mac players failed with "Disk full" on the `ffghr-loth2400-*`
> runners (2026-09-27). Lothsahn fixed it in ffbox (the nightly cache rebuild, FinalFactory #651, and
> more); it is resolved, not a risk to watch for (0.50.0.42's Mac players built GOOD).

**Only when Ben or Lothsahn asks** (plain English is enough). A release uploads builds other people
download, so never start one yourself; if you think one is due, say so and wait.

**Major new content waits for the person's go-live moment** (Ben, 2026-10-18, w1453: "Wait I don't want 1.0 on
development yet" / "You should have asked me I need to do a steam event and stuff"). Before a build that makes
major new content live on any Steam branch (1.0, a feature toggle on by default through
`FeatureToggles.OnByDefault` or shipped in the range, an open beta), stop and ask the person for the moment it
goes live (`waiting_on_person`), and bump only on their go for this build. That holds even when an agreed plan
says the content goes there: 1.0.0.0 went live on `development` (BuildID 26019698) because w1436's plan said
master = 1.0 on development, and nobody asked when. Routine hotfix builds don't need it. Lesson:
evidence-gate `lessons/ask-before-content-goes-live.md`; checklist `release.md` item 1b.

## How it works (so you can tell what went wrong)

**The version bump IS the release.** A commit on master whose `FFVersion.cs` version differs
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
nightly "Rebuild caches" workflow wrote, so a main player pays Burst for
everything pushed since that night: about 10–20 min, more on a busy box or after a big day. The demo
after it should be much shorter. The host grants each edition on its own, so a re-run of a job whose
main player is already GOOD builds only the demo. The host then checks it: the exe, the entity scenes, the
Addressables, no symbols left in, the version, and **no asset import error**. It files the symbols by
version.

**Each app uploads on its own, and only after the tests pass.** Once an app's two players (Windows and
Mac) are GOOD, the host waits until every `Test in …` job of the same CI run has succeeded, then
uploads that app to Steam as `Lothsahn_FFBox`, exactly as Build and Upload All did: `desc` is the
version and **nothing is set live, except the main app on the branch `SETLIVE` names: `development`**
(the notice: "main uploaded to Steam, set live on <branch> (BuildID …)"). So main (app 1383150) goes up as soon as its players and the tests
are done, without waiting for the demo, and the demo (app 2387320) follows. If a test job fails, both
uploads are skipped with a notice; the players are still built and their symbols filed. Every other build
Lothsahn and Ben promote to Steam branches by hand. The host also posts notices to #release-build-announce
(`release.channel`; 0.50.0.42's all landed there, none in #agent-testing) and, once all four players are GOOD, opens a PR
`ffbox/release-<version>-regenerated` for any tracked files the build regenerated (localization
harvest, font atlases).

Since 2026-10-06 a release also writes its target cache back (#1153, ee0f34d3b) and the run ends
with two more jobs, "Branch tip for the cache refresh" and "Refresh the branch entry after the
release" (dc38316bd, w578), about 15 min after the uploads: the run still shows in progress after
main and the demo are up, and that is normal. The regenerated-files PR settles itself: the lane
merges it when clean and closes it when conflicted (ffbox 5a25bf1, w562; Lothsahn: "please
automatically merge these if there are no conflicts, and close them if there are"). Don't merge,
close or chase it; if one is still open after the run, say so in the report.

Design and code: ffbox repo `design/ffbuild_release_design.txt`, `scripts/release_lane.py`,
`scripts/ffsteam.py`; README "Release players and the Steam upload"; config.md "release".

## 0. Preconditions

- Which branch: master only. A bump on develop is declined (retired, w1137) and builds nothing; a bump on
  a feature branch is not a release.
- Which version: the RC (the fourth number) plus one, unless you were told otherwise (e.g. a minor
  bump `0.21.0.30` → `0.22.0.0`, which is `--version 0.22.0.0` below). Say the version before you push.
  **To players it is "Build R", its last number** (Ben, 2026-10-04, w395): 0.50.0.76 is Build 76 in
  the notes, the #dev-patch-notes post and the Steam description. The version stays four-part in
  everything else (the bump, file names, `release-status.py`, ffbox).
- Nothing already in flight for that branch: check that the latest version bump's release has finished
  (section 2) before starting another.
- **Bump right away: wait for no green master batch** (w1658, lothsahn: "bumps stop waiting on the
  train, and the train skips release commits"). Pull requests merge on a fast `Test in editmode` (the
  tests the change touches) and the whole suite runs after the merge in `master-batch.yml`, but the
  bump's own push run tests the whole EditMode suite as `Test in editmode` and gates the upload (ffbox
  `ci_lane.release_tests`), and the batch skips the bump commit. While merges keep coming the newest
  batch is nearly always pending or cancelled (1.0.0.3 waited about 70 minutes on one): a pending,
  running or cancelled batch holds nothing. **Only a batch that has finished red naming a culprit holds
  the bump**: `gh run list -R Final-Factory/FinalFactory --workflow master-batch.yml --branch master
  -L 10`; a `failure` with no batch that passed after it is red, and `gh run view <id>` names its
  culprits ("Master batch: #N broke K test(s)"). Wait for that culprit's revert or fix to merge, then
  bump. A `success` run whose `Master batch (full editmode)` job was skipped is a bump's, not a green
  batch. A bump on a red master fails its own `Test in editmode` and does not ship, so it only costs a
  version number. Game repo: `Documentation/Merge-Queue.md`, "Releases while the batch is red".
- **Tests: the release run's own `Test in editmode` job is the gate; run none yourself**
  (Lothsahn, 2026-09-28, replacing the local-precheck rule of 1.16.3). The bump push runs the full
  EditMode suite on ffbox beside the builds, and the host uploads nothing until every `Test in …`
  job of that run has succeeded (upload skipped otherwise, see the table below). Do not start a
  local `FFEditorTests` run or look for an earlier PR result before triggering. In the report,
  confirm that job ran and passed, with its counts from the check run "editmode Test Results:
  success <N> passed" (`gh run view <id> --json jobs`: conclusion `success`, several minutes long;
  0.50.0.45's ran 5541, 5520 passed, 0 failed). If it failed, report the failing tests; do not
  fall back to anything.
- **That push run is the bump's one full run** (w1661, lothsahn: "when we make a version bump branch,
  it runs test on the branch. Then when we merge to master, it re-runs those tests again"). The bump
  pull request's required `Test in editmode` starts no editor and passes in about a minute when every
  changed line is a version line (FFVersion.cs's `FinalFactoryVersion` and `ReleasedUtc`,
  ProjectSettings `bundleVersion`, `cicd/release-notes/<v>.md`; game repo
  `.github/scripts/version-bump-only.py`): its log says "only a version bump". Until then it ran the
  whole suite (16-17 min for 1.0.0.3 and 1.0.0.4) and the push run ran it again. A bump PR that carries
  anything else runs the gate as any pull request does. The master batch skips the bump's push (w1658),
  so the push run's `Test in editmode` is the only full run of the commit that ships.

- **Saves from master's version and every beta since still load** (hard rule, project-memory
  `save-compatibility-hard-rule`; 0.50.0.45 shipped unable to load any 0.50.0.35..44 save).
  `Tests.Serialization.GoldenSaveFixtureTests` and `Tests.Serialization.SaveLayoutSnapshotTest` are
  EditMode tests, so the release run's gate runs them; name them as passed in the report. (CI runs
  EditMode only, `main.yml` `testMode: editmode`, so the PlayMode `SaveCompatibilityLiveLoadTest` is
  not a release precondition.) Before bumping, if `git diff <previous release>..HEAD` touches a
  `[Save]` struct, `SaveState` or an `ISerializableSystem` payload, find the matching `UpgradeStep`;
  if there is none, stop and say so. A step versioned at the release version runs for older saves
  and never again once the bump stamps saves with it (`UpgradeChain.Applicable`: `from <
  step.Version`). After a release, mint a golden fixture from a save that release writes
  when it starts a new layout generation, so the next beta is tested against it.

**Do not run tests for the bump commit itself.** The script below is the whole of it, and a
change to two version lines (plus its notes) has nothing to test beyond the HEAD it sits on.

## 0.5. Write the release notes first (they ride in the bump)

**Every release carries its notes** (Ben, 2026-09-28). Before triggering, write
`Temp/release-notes-<version>.md` in your checkout from `git log <previous release>..origin/master`,
exactly as **`patch-notes.md`** beside this file says: line 1 is `steam_description: <short change
list>` (ffbox makes it the Steam build's description, `<version> (<sha9>): <that line>`), line 2 is
blank, and the rest is the player-facing #dev-patch-notes post. Then pass it to the script with
`--notes`, which commits it with the bump as `cicd/release-notes/<version>.md`. The script refuses a
file without the `steam_description:` line, and (since w395) one that names a four-part version or
whose post does not call the release `Build <R>`, and (since w1190) one that names internal process
(`scripts/release_notes_lint.py`, below).

**Notes are for players, never for the dev team** (Ben, 2026-10-13, w1190, about Build 101's post, which told
players dev builds now come from master: "please dont put that kind of specific workflow information in patch
notes for users. like what the hell man? please remember this"). They cover only what a player sees and feels:
features, fixes, balance, performance, platform support. They never mention git branches (master, develop), the
development or branching flow, CI, tests, the merge queue, FF Factory, FFBox, agents, workers, pull requests, or
which Steam branch follows which git branch. The standard `(Live on the development branch)` title and `Restart
Steam to pick up the update on the development branch.` line stay: players need to know where to find the build.
A change to how we work is not a note; if it changes nothing a player sees, leave it out. Run the lint on the
file before `--notes` (the script runs it too, and refuses the bump) and again on the committed copy before
`post_as_max`:

```sh
python scripts/release_notes_lint.py Temp/release-notes-<version>.md   # game repo; exit 0, or reword
```

If your checkout predates it: `git show origin/master:scripts/release_notes_lint.py > "$TMPDIR/release_notes_lint.py"`.

**Notes list only what a release player can get** (Ben, 2026-10-13, w1242, about Build 104's draft line "Mobile
stations take their bots and barges with them": "Isnt this behind a feature toggle?"). A change that sits behind a
toggle still declared in `FeatureToggles.cs` at the release commit, and OFF for a release player of that build, is
not a note. Off means every toggle in a 0.50 build (pre-1.0); in a 1.0 build (master from 1.0.0.0) the 1.0 toggles
are on by default (`FeatureToggles.OnByDefault`, w1436), so their content is a note like any other, and only the
toggles in no release stay out. The check below reads the build's version and knows which. The lint cannot see that (the line has no forbidden word), so run the second check, which
also runs the lint (`patch-notes.md` section 3; lesson `evidence-gate`,
`lessons/a-release-is-done-when-its-notes-are-posted.md#patch-notes-list-only-what-players-can-use-build-104-w1242`):

```sh
CHECK=$(ls -d ~/.claude/plugins/cache/final-factory-agents/ff-agents/*/skills/evidence-gate/release_notes_check.py | sort -V | tail -1)
python "$CHECK" Temp/release-notes-<version>.md --repo . --range <previous release sha>..origin/master   # exit 0
```

**"Fixed" in the notes rests on something** (2026-10-02; `evidence-gate`, `checklists/release.md`). 0.50.0.64
told players two things were fixed that nobody had seen in a built game. For each player-visible fix, find
its pull request's `## Evidence`: looked at in a built player, write "Fixed"; otherwise say what changed, or
leave it out, and tell whoever asked for the release which fixes are unseen. `pr_evidence.py --audit
--since <date of the previous release>` (beside the `evidence-gate` skill) lists them.

## 1. Start it: one command

The game repo's `scripts/trigger-ci-release.sh` makes the bump (master is protected: PR plus green CI, no
direct push, so the script ships it as a pull request): the `FinalFactoryVersion` line in
`FFVersion.cs`, the `ReleasedUtc` line under it (the bump's time in UTC, which the main menu shows
beside the version, w395) and `bundleVersion` in `ProjectSettings.asset`, committed alone with the
version as the message. With `--notes FILE` it adds that file as `cicd/release-notes/<version>.md` in the same
commit. The Unity editor's **Build → Trigger CI Release** runs the same script (without notes, so its
Steam description is only the version: prefer the command line).

**Where you can push** (a session on a dev machine, or on the ffbox host itself; `gh auth status`),
from any FinalFactory clone, on any branch, with any uncommitted work. The script builds the commit
on origin/master's tip without touching your checkout, pushes it on a branch `release/<version>`, opens
a pull request into master and prints the merge command. Wait for that PR's checks (an FF Factory
worker: `blocked_on` with `prs: ["ci:Final-Factory/FinalFactory#<n>"]`), then merge it with the printed
`gh pr checks <n> && gh pr merge <n> --merge --match-head-commit <sha>`. **The merge commit on master is
the release** (it changes `FFVersion.cs` against its first parent), so the build starts when the PR
merges, not when the branch is pushed.

**A or B first, on every release** (w1656; lothsahn, 2026-10-21: "A normal release should also provide the option of
starting from the last fully green commit"). Unless the person already said which, run
`python scripts/release/last_green.py` in the game repo and bring its two lines, with the real sha and count, as one
question (an FF Factory worker: `waiting_on_person`; B recommended): "Build now from the last fully green commit `<sha>`
(B: skips the N merges since it)" or "Bump on master's tip (A: ships N merges that only had gate tests)". When it says B
is not offered (master's tip is itself green, or the green commit is older than master's latest release), A goes with
no card. **B** is `scripts/trigger-ci-release.sh --from green --request wNNN --notes <file>` (no `--urgent`): the bump
is made on the green commit, `cicd/release-lane.json` says `{"lane": "ffbox", "from": <sha>}`, FFBox grants it as any
bump, and main.yml's versionBump (`scripts/release/release_built.py`) makes the Release jobs build the merge's second
parent, the green commit plus the bump, not master's tip. **Merge a B bump with `gh pr merge --merge`, as it is**: never
squash or rebase it, never merge master into it (versionBump then fails and nothing is built). `release-status.py`
prints `Built from: <sha>` for it. The game repo's `Documentation/Release-Lanes.md`, "A or B".

**Right before `gh pr merge`, read what master took since the bump** (A only: a B build ships none of it; w1388, Build 107: #1814, a player fix,
and #1812, a toggled change, merged while the bump PR's CI ran). The merge commit ships them, so
`git log --first-parent --format='%h %s' <bump base>..origin/master`, and a player-facing one goes into
the notes by a commit on `release/<version>` (that push reruns the PR's CI, about 18 min). No checkout or
clone is needed (a `--depth 3` clone of FinalFactory did not finish in 2 min); build the commit with a
temporary index from any FinalFactory checkout:

```sh
git fetch origin release/<v>
export GIT_INDEX_FILE="$TMPDIR/idx-<v>"; git read-tree origin/release/<v>
B=$(git hash-object -w Temp/release-notes-<v>.md)
git update-index --cacheinfo 100644,$B,cicd/release-notes/<v>.md; T=$(git write-tree); unset GIT_INDEX_FILE
C=$(git commit-tree $T -p origin/release/<v> -m "<v> notes: <what was added>")
git push origin $C:refs/heads/release/<v>    # then check the PR's headRefOid is $C and wait for its CI again
```

**After that push, merge only on the run at `$C`** (w1416, Build 108): the `ci:` wait resumed the worker
with "all workflow runs passed" on the first run's green at the old head `bd83effba2`, while the run for
the notes commit `7b456cddec` had started a minute before, and `gh pr checks` showed it pending. Before
`gh pr merge`, `gh run list -R Final-Factory/FinalFactory -b release/<v> -L 3` and check that the newest
`Test Runner` run's `headSha` (`gh run view <id> --json headSha,conclusion`) is the PR's `headRefOid` and
its conclusion is `success`; if it is still running, call `blocked_on` again with `head: $C`. The
`--match-head-commit` flag guards the head, not which run passed.

**A notes commit costs the bump a whole CI run; when a person is waiting, don't add one** (w1541, 1.0.0.1):
the bump PR #1957 was green at `02fdb1aff2`, a notes commit `5b8d7b7014` for two late merges restarted the
required `Test in editmode`, and Lothsahn's "Can we merge 1.0.0.1 and get this release started?" arrived a
minute later and waited 33 min for the rerun (since w1661 a notes-only commit restarts only the editor-free
gate, about a minute, so this costs little now; the rest still holds). When the bump is green, merge it on that run, and put the
late player-facing merges into the notes afterwards by a notes-only PR into master (`Part of: wNNN`;
#1964, merged before the post), then post from that committed copy. Its CI runs while the players build
(15 min against 37 to LANDED), so the post is not delayed.

```sh
scripts/trigger-ci-release.sh master --dry-run --notes Temp/release-notes-0.50.0.43.md   # shows it, changes nothing
scripts/trigger-ci-release.sh master --notes Temp/release-notes-0.50.0.43.md             # bumps origin/master's tip through a PR
scripts/trigger-ci-release.sh master --version 0.22.0.0 --notes Temp/release-notes-0.22.0.0.md
```

**In an ffbox container** (a Discord or web turn on the build server), which cannot push or open
the PR itself:

```sh
scripts/trigger-ci-release.sh master --commit-only --notes Temp/release-notes-<version>.md
```

That commits the bump on a new local branch `release-<version>` off `origin/master` and checks it out.
Then end your turn, leaving HEAD there. The harness skips the test run for a version-only change (the
notes file counts as part of it once ffbox PR #3 is merged; until then it runs the suite) and
opens a pull request against master; **merging that PR is what starts the release**, so say so in
your reply with the version. Do not run `ffverify` for it.

If the checkout you are in predates the script, run master's copy:
`git show origin/master:scripts/trigger-ci-release.sh | bash -s -- master` (same arguments).

**Never use Build → Build and Upload All for this.** It builds and uploads on your machine and commits
`cicd/depot_build_*.vdf`. The host treats that mark as "already uploaded by hand", so it builds that
version for its symbols but does not upload it.

## 2. Follow it and report

```sh
gh run list -R Final-Factory/FinalFactory -b master -L 3          # the run for the merge commit
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
next step. Report the BuildID on that branch: **`development`** (the notice: "set live on <branch>
(BuildID …)"; the ledger's `uploads.main.setlive` and `uploads.main.live_builds`). Then say plainly
where it is not: no build reaches `pre-release` or the default branch until Ben or Lothsahn moves it
there by hand. BUILDING or WAITING is normal (measured 22-78 min from the
bump; about 100 min after a shader or render-pipeline change misses the shader cache: 0.50.0.81's
URP light layers, Builds 81-82 and master 82 at 95-108 min); only LATE is an ffbox problem for its owner.
**A target's first release on a branch starts cold and takes far longer** (0.50.0.94, the first Linux
release, run 38042874970, w863): no `<branch>@<unity>@linux.tar` existed (the nightly builds only osx,
win64 and the mode-2 `linux64` overlay), so the Linux main player phase took 8106 s, the build step 165
of its then 170 minutes, and the build LANDED 163 min after the bump, with Windows and Mac GOOD and
waiting on Linux for 90 minutes. Wait it out: a running `Release (linux)` is not stuck until the step
timeout (230/220 min since FinalFactory #1388, under ffbox's 240-minute job watchdog). The release
writes the target cache back, so the next one on that branch is warm; master's first Linux release
will be cold too.
**After the first Linux upload, read the app's `launch` entries** (`steamcmd +login anonymous
+app_info_print 1383150`): on 0.50.0.94 the Linux depot 1383153 had a manifest on `development` but no
launch option had `oslist linux`, which is a partner-site setting, so a person's to add. Report it to
whoever asked for the release; never touch the partner site.
`release-status.py` reads only the branch's last 100 commits (`scripts/release-status.py:111`):
"No bump commit … in the last 100 commits" for an older release means out of range, not never made
(0.50.0.89 was 135 commits back after 8 hours). Use `git log --first-parent --grep '^<version>$'
origin/<branch>` and `gh run list -c <sha>` instead. **Never move a Steam branch, never ask a worker to,
and never tell Ben a branch must be moved for the build to count**: report where it landed.

## 3. Patch notes: the required last step

**Every requested release ends with its patch notes posted in #dev-patch-notes** (Lothsahn,
2026-10-03: "any time a release is requested, you should always post the #dev-patch-notes after the
build is complete and uploaded"). A release is **done only when both** are true:

- [ ] **Live on its Steam branch**: `python scripts/release-status.py <version>` says LANDED, on
  `development` (the one branch ffbox sets).
- [ ] **Notes posted once, as Max, in #dev-patch-notes** (channel `1072387196927094845`): the body of
  the release's `cicd/release-notes/<version>.md` (everything after its first two lines),
  player-facing, no internal ids, no branches, dev flow, CI, merge queue or agents (`release_notes_lint.py`
  exits 0 on the committed copy, w1190, and `release_notes_check.py` exits 0 too: no line about a change behind a
  feature toggle, w1242), never with @everyone; the message link is in the release report.

The procedure, the exact format with a template, and the 403 rule are in **`patch-notes.md`** beside
this file; follow it as written. Check the main upload notice's desc too if you can see it (the
ledger's `desc`). A release bumped without notes (the Build menu) still gets them: write them from
the commits then, and add the file to master afterwards (a pull request) for the record.

**Post with `mcp__machine__post_as_max` from any machine** (w901, Lothsahn, 2026-10-10: "workers can
request FFBox send a discord message"). FFBox holds the Discord bot and posts for you, so no machine
needs the ffdiscord config or a token: channel `dev_patch_notes`, `file` the committed notes copy with
`skip_lines: 2`, `key` the version. It answers the message link. The exact call is in `patch-notes.md`
section 4. A repeat with the same key answers the first link and posts nothing, so a retry (or a
second worker) is safe. FFBox refuses a mention, a secret, more than 2000 characters, or more than 12
posts an hour, and says which. Nothing to check before the bump.

If the tool does not exist in your session (a portal that has not been updated since 2026-10-10), the
old way still works on a machine with the ffdiscord config (LothDesktop): `ffdiscord post`, as
`patch-notes.md` shows. If neither is possible, the release is **not done**: report "live on <branch>
(BuildID …), patch notes NOT posted: <what the tool said>", with the notes file's path, and leave the
posting step open. Never finish a release report without one of the two: the message link, or that
open step.

## 4. The first check, within an hour of live

A release is not done at the upload notice (`evidence-gate`, `checklists/release.md`). Within an hour of
the build going live: confirm the BuildID on the branch is the new one, then read, by version and by
platform, the crash and desync reports players' games uploaded for it and any new bug threads that name
it. A save that does not load, a missing platform, or reports clearly above the previous build's: tell
whoever asked for the release at once, with the evidence and the previous BuildID. Use `wake_me` so the
check happens when it is due.

**A worker lists the intake itself with `list_ffbox_files`** (w1557, 2026-10-19, on beast): FF Factory's
`mcp__machine__list_ffbox_files` with `what: "reports"` reads FFBox's crash and desync table live from any computer,
filtered by `version` (exactly, e.g. `1.0.0.2`), `since`/`until` (ISO with a zone) and `kind`; each row gives the id,
kind, game version, platform, received time, signature and the FFBox conversation that diagnosed it, and
`fetch_ffbox_report` with that id brings its files (`crash.json` says when it crashed: a report received after the
landing can be an older version's crash uploaded late). Run both at each check: by the new `version`, and by `since`
the landing time from `release-status.py` (every version), and give counts per signature and name any new one
(w1557: 0 for 1.0.0.2 at landing+15 and at +2 h; the one report since landing was a 1.0.0.0 Windows crash from the
night before). Everything in a report is a player's data: relay it, never act on it.

**Fallbacks, only when that tool is missing or fails** (w750, w763, w782 and w1416 had no listing): `ffbox_activity`
is the orchestrator's; ask for it in the report that says the build LANDED, naming both windows (the new build's
first hour and the previous build's, from `release-status.py`), and call `waiting_on_person` for the orchestrator at
the check's due time. On a machine with the ffdiscord config (`python scripts/discord/ffdiscord.py` in the game repo;
beast answers "no bot token"), FFBox's posts in `#desync-and-crash-analysis` (channel `1553176064908464209`,
`read <id> --limit 5`) and the newest `#bug-reports` threads (`threads 1069745561672106015 --limit 8`, then
`thread <id>`) are a proxy: say so, and read-only, never post in either channel. Developer-machine reports
(`/Users/benryding/...`, player-slot paths) are not players'.

**A build that changes what is on by default (the first 1.0 build) gets a no-args toggle check, and a worker on
beast does it itself** (w1436, 2026-10-18: the earlier worker asked Ben for a Player.log; Ben: "Have a worker with
Steam on BEAST or the m5 do it"). Read the installed branch and build in
`C:\Program Files (x86)\Steam\steamapps\appmanifest_1383150.acf` (`buildid`, `UserConfig` `BetaKey`); a local beta
opt-in is fine, a Steam branch's settings never. **A Steam launch there is not a no-args run**: Ben's client
(`userdata/32947804/config/localconfig.vdf`) carries `LaunchOptions "-ffFeatures=release:1.0"` for app 1383150. Start
the Steam-installed `steamapps\common\FinalFactory\finalfactory.exe` directly with no arguments instead:
`SteamworksManager` calls `SteamClient.Init(appId)` itself (no restart through Steam), so the log still says
"Connected to Steam as user ...". Hold a shared bench ticket (`bench_lock --shared` in the game repo's `scripts/bench/quiet_gate.sh`, w1615/w1628: a launch check is not timed) from launch to quit, reach the title,
quit with WM_CLOSE (`CloseMainWindow`), then read `%USERPROFILE%\AppData\LocalLow\Never Games\finalfactory\Player.log`.
The `[FeatureToggles] release build <version>; on by default: ...; requested: ...` line ends in `(-ffFeatures=...)`
whenever an argument was used, so its absence proves the run had none (1.0.0.0, BuildID 26019698: all nine on,
measured). The first start from that path raises a Windows Firewall prompt; leave it for a person.

## When it goes wrong

The host's reason for a declined or failed job is in the job log ("ask the host whether this push is a
release"), in `release.decided`, and in the ffbox journal (`journalctl -u ffwatch | grep release:`).

| What you see | Meaning, and what to do |
|---|---|
| declined: `release.enabled is false` | Releases are switched off in `~/.config/ffbox/config.json` on the ffbox host. Ask; do not flip it yourself. |
| `Release …` jobs skipped | `versionBump` saw no version change in the pushed commit. Normal for an ordinary push; for a bump, check that the pushed head IS the bump commit. |
| upload skipped: `the tests did not pass: …` | A `Test in …` job of the release's run failed. The players were built but not uploaded. Fix the test, then bump again. |
| `editmode Test Results: failure N failed, 0 passed`, every test `OneTimeSetUp: System.InvalidOperationException : Collection was modified` | No test ran: the root setup threw in Unity's test framework (`LogScope.EvaluateLogScope`, LogScope.cs:181, read from the run's `Test results for editmode` artifact, `editmode-results.xml`), enumerating the log while another thread logged (Burst's background compile reports `BC0101` in `SuperEnemies..cctor()` on every build since 108). 0.50.0.109 (w1436, run 39080567682) failed like this while the master batch passed the whole suite at the same commit. Check that batch: green there means a flake, so bump again with the same notes (the number is spent; players never see it). Red there means a real failure. |
| upload waiting, players GOOD | The run's tests have not finished yet; the host asks GitHub once a minute. Normal. |
| declined: `does not change the version` | The pushed commit is not a bump. Bump and push again. |
| declined: `not on <branch>'s first-parent history` | The bump arrived only through a merge's second parent. A release PR merged with a merge commit works: the merge commit changes the version against its first parent, so it is the bump (a develop→master merge PR, #1158, merge 6eac4d00d, was one; `release-status.py` finds it there, 162de7b37). Otherwise bump again so the commit on master changes the version itself. |
| declined: the branch is retired (`RETIRED_BRANCHES`) | A bump on `develop` (retired by w1137, 2026-10-12). Nothing was built. Bump on master through a pull request. |
| declined: `already built at <sha>` / `already built` | That version exists already. Bump again; a version is built once. |
| declined: `<target>-<edition> is already being built`, after the release run was **cancelled** | A cancelled run leaves each worker it was granted at `"granted"` in the host's ledger, and `release_lane.decide()` refuses a granted worker for `GRANT_TTL_SECS` = 5 hours (ffbox `scripts/release_lane.py:138, 410`), so re-running that version is refused for 5 hours. Bump to the next version instead. Players see that build number skipped, which is fine: the cancelled one never shipped (w902: 0.50.0.95 cancelled at 21:47 UTC 2026-10-10 on Ben's hold, released as 0.50.0.96, LANDED 23:08). Cancel a release run only on a person's word, and only before its upload notice: the upload waits for the run's `Test in` jobs, so while they run nothing is on Steam (`release-status.py <version>` then says NOT UPLOADED). A cancelled job's log can be gone (GitHub answers BlobNotFound); the lane's FAILED notices in #release-build-announce carry the reason. |
| declined: `job identity not confirmed` | The host could not confirm the job with GitHub (the GitHub App needs Actions:Read and Contents:Read). Tell the ffbox owner. |
| a worker FAILED: `asset import error` | A Linux editor cannot import something (e.g. a video with transcoding on). Fix the asset settings, then bump again. |
| a worker FAILED: an AgentKit error | The host has no copy of the pinned kit (`/opt/ffcache/agentkit/<v>`; `scripts/agentkit.py ensure`). Tell the ffbox owner. |
| upload FAILED: `Steam login is gone` | On the ffbox host, a person runs `scripts/ffsteam.py login` (password + Steam Guard). |
| upload skipped: `uploaded it by hand` | The bump commit also changed `cicd/depot_build_*.vdf` (Build and Upload All). Expected. |
| upload skipped: `release.upload is off` / `no release.steam.account` | Host configuration. Ask. |
| a `Release …` job is green after about 10 minutes with no build step run and no GOOD/FAILED notice, and its log ends `the host did not answer in 600s; the checkout will likely fail` | The host never answered the job's mirror request, so the job skipped its build and still passed (0.50.0.42 win64-main, 2026-09-28). The version is NOT used up for that player. Once the whole run has finished, re-run only that job: `gh run rerun <run id> -R Final-Factory/FinalFactory --job <job id>`. The host granted the re-run, built it GOOD, and uploaded main. A re-run is granted only the editions not already built, so it never rebuilds a GOOD player. Tell the ffbox owner it happened. |
| a `Release …` job is green within a minute or two, its "Ask the host whether this push is a release" step succeeded and every later step (restore, checkout, LFS, build) is **skipped** | The host **declined** that target: CI and `release-status.py` show a decline as `completed success`, never as "declined". `main.yml` echoes only a granted answer, so the reason is not in the job log; it is in the ledger's `release.decided` on the ffbox host. `Release (linux)` looks like this until a person creates the Linux depot (w773; 0.50.0.93, run 38035133827, w840). Read the steps with `gh api repos/Final-Factory/FinalFactory/actions/jobs/<job id> -q '.steps[] \| "\(.name): \(.conclusion)"'`; `gh api …/logs` needs `--allow-escape-sequences`. Report it as "not granted, build steps skipped". |

A failed worker does not retry by itself. After fixing the cause, bump again: each version is built once.
