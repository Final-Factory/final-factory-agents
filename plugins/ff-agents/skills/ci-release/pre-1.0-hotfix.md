# A pre-1.0 hotfix: a fix for the production build while master is 1.0 (w1436)

Ben, 2026-10-17: "After the next build I want to create a branch pre-1.0. we will use that to fix any bugs we find on
production until we release 1.0." / "any bug fixes that are essential will be cherry picked to the pre 1.0 branch in
the mean time for hot fixes but the plan will be to get 1.0 out (master branch) in a few weeks" / "When we do the open
beta for development branch we will want to bump the version to 1.0.0.0 too". The game repo's
`Documentation/Pre-1.0-Hotfixes.md` is the full reference; this is the release side.

| Line | Git branch | Version | Toggles in a release player | ffbox on a bump | Steam |
|---|---|---|---|---|---|
| 1.0 | `master` | 1.0.0.R (first bump after the cut: 1.0.0.0) | every 1.0 toggle on (`FeatureToggles.OnByDefault`) | builds, uploads, sets main live on development | development |
| production | `pre-1.0` | 0.50.0.R, R going on from the cut | every toggle off | builds, uploads, sets **nothing** live (`release_lane.UPLOAD_ONLY_BRANCHES`) | default, set by Ben or Lothsahn by hand |

## The route

1. **The fix lands on master first**, as any fix, through its own PR. FFBox's own fix runs keep branching from
   master too.
2. **Essential?** A crash, a desync, a save that will not load or loses work, a progression blocker, or a regression
   players hit on the production build. Anything else waits for 1.0. The request's person decides when unsure.
3. **Cherry-pick PR into `pre-1.0`**: a branch off `origin/pre-1.0` (`mcp__machine__switch_branch` in a sandbox),
   `git cherry-pick -x -m 1 <the master PR's merge commit>`, then `gh pr create --base pre-1.0`, title
   `[pre-1.0] <the master PR's title>`. Its body carries `Cherry-pick of #<n>`, **every `Discord:` and `Report:` line
   of the master PR, copied exactly** (FFBox reads every merged PR, whatever its base, and tells each named thread
   again, this time about the hotfix; no label is read), `Request: wNNN` or `Part of: wNNN`, and the `## Evidence`
   section for a player-visible change. Same CI gate as master; merge on green.
4. **The hotfix release**: `scripts/trigger-ci-release.sh pre-1.0 --notes Temp/release-notes-0.50.0.<R>.md`, then
   merge its PR into `pre-1.0` (`gh pr merge <n> --merge`). The script refuses a version of 1.0 or above there.
5. **Follow it**: `python scripts/release-status.py 0.50.0.<R>` (or `--branch pre-1.0`). The verdict is BUILT with
   nothing set live; the BuildIDs are in FFBox's notice in #release-build-announce ("Release 0.50.0.R: main uploaded
   to Steam, nothing set live: BuildID N"; anonymous steamcmd cannot see a build that sits on no branch).
6. **Ask Ben or Lothsahn to set the main app's BuildID live on default** (and pre-release, if they want it there), on
   the partner site. Agents never do it. That ask is a `waiting_on_person` for an FF Factory worker.
7. **Post the notes as Max once default carries it** (`release-status.py` shows default at that BuildID): the title
   says **Build R**, the restart line names the default branch.

## Numbers

- Master's next bump after the cut is **1.0.0.0** without `--version`: `trigger-ci-release.sh` makes it so once origin
  has `pre-1.0`, refuses a 0.50 version on master, and refuses 1.0.0.0 while master's `FeatureToggles.cs` has no
  `OnByDefault`. Notes for that line say **"1.0 Build R"** ("1.0 Build 0" for the open beta).
- Hotfixes keep **"Build R"**: Build 110, 111, after the cut's Build 109.
- The two lines never share a version, which FFBox's ledger (`<branch>/<version>`), its regenerated-files branch and
  its "coming in" notices need.

## Patch notes per line

The rule is still Ben's w1242 one, "only what a release player can get" (`patch-notes.md`), applied to each build:

- **1.0 build**: the 1.0 toggles are on, so their content goes in like any change; a toggle in no release stays out.
  `release_notes_check.py` reads the release commit's version and flags only toggles still off there. The open
  beta's notes (1.0 Build 0) also say: saves made on development cannot be opened on default (copy one first);
  development and default players cannot play together; mods need a 1.0 build from their author
  (`FFVersion.IsSaveCompatible`, `PeerCompatibilityToken`, `ModLoader.LoadModInfo`).
- **Hotfix**: only the cherry-picked fixes; every toggle is off there, so nothing behind one.
