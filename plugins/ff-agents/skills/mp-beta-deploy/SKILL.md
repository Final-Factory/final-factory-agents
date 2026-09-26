---
name: mp-beta-deploy
description: FALLBACK ONLY — the manual M5 procedure that builds the multiplayer Mac + Windows players from develop and uploads them to the password-protected Steam `multiplayer-closed-beta` branch (pre-steps, both builds, verification, depot staging, steamcmd upload, record). The NORMAL route to a new closed-beta build is a develop release through ci-release: develop's players have multiplayer (#613/#614) and ffbox sets the main app live on multiplayer-closed-beta by itself (ffbox a7809f9e1). Use this skill only when Ben asks for a beta build AND ffbox cannot make it (ffbox down, its release lane broken, the Steam set-live failing), or Ben asks for a special build that must not come from a develop release (a branch other than develop, a build with local-only changes). Never start it on your own initiative or as a side step of other work.
---

# Deploy a build to the MP beta branch

**Only when Ben asks** (plain English is enough — he never has to type the skill name). This publishes
a build that other people download, so never start it on your own initiative; if you think one is
needed, say so and wait for him to ask. Proven end to end on 2026-09-23 (0.50.0.21, develop `f594db63d`, BuildID 25471784); both players built on the M5 on 2026-09-25 (0.50.0.28, `75afa459d`, BuildID 25540837).

**Fallback only (Lothsahn, 2026-09-26).** A develop release through `ci-release` IS the closed-beta
build now: develop's players have multiplayer (`FF_ENABLE_MULTIPLAYER_BUILD` in develop's
ProjectSettings, #613/#614) and ffbox sets the main app live on `multiplayer-closed-beta` as it uploads
(ffbox `a7809f9e1`, `release_lane.SETLIVE`). Asked for "a new beta build", use `ci-release` on
develop. Come here only when ffbox cannot do it (host down, release lane or the Steam set-live
failing) or for a special build that must not be a develop release; say which in your report.

**Both players are built on the M5, never on BEAST** (Ben, 2026-09-25, standing rule): the M5
builds both the PC and the Mac versions, so every beta build comes from it. (Releases to the
default app are not built here or by hand at all: CI builds and uploads them on ffbox, via
`ci-release`.) Do not build an upload player on BEAST or in an
ffsb sandbox, even when the M5 is busy: wait for it, or ask Ben. BEAST sandboxes still build
test-leg and play-client players (`honest-coop-play`), which are never uploaded.

**Branch and sign-in (Ben, 2026-09-25, supersedes older notes below where they differ):** the MP beta
branch is **`multiplayer-closed-beta`**, never `development` (another branch on the same app). Uploads use
steamcmd on the M5, and Ben signs in through the Steam app on the M5 when steamcmd prompts, so agents
need no Steam password and never ask for one: when steamcmd wants a sign-in or approval, stop and ask
Ben to sign in or approve it, then carry on. The branch's tester password (for
`app_update 1383150 -beta multiplayer-closed-beta -betapassword <pw>` to install or verify the build as
a tester) is deliberately NOT in this public repo: it is in the private game repo, 068 `tasks.md` T041,
or ask Ben.

**Why this is not the Build menu:** "Build and Upload All" uploads to the DEFAULT branch and commits
`cicd/depot_build_*.vdf` (which makes ffbox skip that version's upload). Since #613/#614 the Build menu
no longer strips `FF_ENABLE_MULTIPLAYER_BUILD`, but it is still not the route for this. Never use it here. The
repo's documented multiplayer build path is `Editor.LocalMultiplayerVerificationBuild` (README
"Multiplayer Menu Visibility"). It skips the main script's extras, so this skill runs them by hand to
match `BuildCommand2.BuildAndUploadAllInternal`. No other shortcuts ("no hacks" — Ben).

## 0. Preconditions
- You are on the M5 (rule above).
- develop is pushed and in sync (`git fetch && git status -sb`). The build source is a pushed commit.
  Never commit Ben's unrelated local edits (the two `.mat` files, `ProjectSettings.asset`).
- Pin the Unity MCP instance whose `path` is this repo (`ff-agents:editor-ops`). Editor not playing,
  not compiling; standalone define includes `FF_ENABLE_MULTIPLAYER_BUILD`, active target StandaloneOSX
  (else run `LocalMultiplayerVerificationBuild.PrepareMacMultiplayerBuild` in a batchmode pass first).
- **Pulling develop drops the define, and a running editor keeps stale settings.** Resetting
  `ProjectSettings.asset` so the fast-forward can go through removes the local
  `FF_ENABLE_MULTIPLAYER_BUILD`. An editor that was open during the pull still holds the OLD
  ProjectSettings (e.g. a stale `bundleVersion`) in memory and can write them back. So after the pull:
  stop the editor, run the batchmode `PrepareMacMultiplayerBuild` pass (~1 min), start the editor, then
  check that `PlayerSettings.bundleVersion` equals `FFVersion` (2026-09-25).
- No honest-coop sitting mid-build on the same editor.

## 1. Pre-steps (in the editor)
Run, in order, via `execute_code` (reflection on `Editor.*`), writing a marker file:
`Editor.Localizer.HarvestAndExport()` → `Editor.FontCoverage.RebuildFontAtlases()` →
`Editor.FontCoverage.ValidateFontCoverageOrThrow()`. A failure aborts the deploy. Commit whatever they
change (e.g. rebaked CJK font atlases under `Assets/UI/Fonts/`) and push — that commit is the source.

## 2. Mac player (in the editor)
1. Call A: `AssetDatabase.ImportAsset("Assets/Scenes/main/EntitySubScene.unity", ForceUpdate |
   ForceSynchronousImport)`.
2. Call B (SEPARATE call — in one call the build races the entity bake and ships only `scene_info.bin`):
   `BuildPipeline.BuildPlayer` with the enabled scenes, `StandaloneOSX`, `BuildOptions.Development`,
   into a fresh `cicd/mp_beta_stage-<sha7>/mac_main/finalfactory.app`, appending `returned result=…` to a
   marker. The bridge times out before it ends — wait on the marker, never re-issue the call.
   Keep the "refuse if the stage dir exists" guard at the top of call B (see the redispatch gotcha below).
3. **Expect the FIRST build after call A to be bad, then plan on two builds.** This reproduced twice on 2026-09-23
   (0.50.0.24 and the t89 test player). The worker bakes the subscene DURING that first build (the log shows
   `Baking the Entity Prefab Container` after it starts), so it ships only `scene_info.bin` (~2617 MB against a
   good ~2775 MB). An immediate second build is good. Either run a throwaway first build, or let the bridge
   re-dispatch (item 4) and verify.
   **Check `EntityScenes/` right after every build (§4), not only at the end.** On 2026-09-23 (0.50.0.24)
   a build made from a SEPARATE call B, right after call A, still shipped only `scene_info.bin`. If that
   happens, move the stage aside as `…-BAD-noentityscenes` and re-run call A. The editor log must then
   show the subscene bake (`Baking the Entity Prefab Container`, then `Streamed scene … .entities`)
   before you run call B again.
   On 2026-09-25 (0.50.0.28) the FIRST build after call A was already good (entity scenes present,
   15 min), and the second build was incremental (15 s) with an identical file list. So the first build is
   not always bad: check each build, and keep the good one.
4. **The bridge can RE-DISPATCH a timed-out call B.** The same day, a second `BuildPlayer` started 27 s after
   the first returned (16:15:47 vs 16:15:20 UTC) and wrote a fresh stage dir. Never assume only one build
   ran. The marker can hold several start/`returned` pairs, or reappear after you move the stage aside.
   Before you stage anything, confirm that every file in the stage has an mtime from the build you trust
   (`find <app> -newermt '<local start time>' -type f | wc -l` equals the file count; `-newermt` is LOCAL
   time).
   The re-dispatch is routine: 0.50.0.28 saw 5 refused re-dispatches after build 1 and 3 after build 2.
   The reply you actually get back can be one of those refusals ("refused: stage exists") even though the
   real build succeeded, so read the verdict from the marker, never from the reply.

## 3. Windows player (on the M5)
Build it on the M5 from the same source sha as the Mac player (rule above). The repo's entry points are
`Editor.LocalMultiplayerVerificationBuild.PrepareWindowsMultiplayerBuild` and then
`BuildWindowsMultiplayerDev` with `-ffVerificationBuildOutput <stage>/windows_FinalFactory/finalfactory.exe`
(`Assets/Editor/LocalMultiplayerVerificationBuild.cs`), as two SEPARATE batchmode sessions with the editor
closed. The prepare pass switches the active target and adds `FF_ENABLE_MULTIPLAYER_BUILD` to
`ProjectSettings.asset`; never commit that edit. Wait on a status file (`prepare rc=`, `build rc=`, `done`),
never on the bridge. Run the two passes from one detached script (`nohup … &`) that refuses if the
output dir exists or the editor is open (`Temp/UnityLockfile`).
First M5 run (2026-09-25, 0.50.0.28): the prepare pass took 2m44s and the build 17m39s, both rc=0, with
0 `error CS`. The build ships the Mono player, and Unity 6000.3.19f1 on the M5 has
`WindowsStandaloneSupport` (Mono variations only). That is enough because Standalone scripting is Mono
(`ProjectSettings.asset` `scriptingBackend: Standalone: 0`). Gotchas:
- `BuildPlayer` DELETES the output file's parent directory before building
  (`LocalMultiplayerVerificationBuild.cs` `BuildPlayer`). Point it at its own `windows_FinalFactory/`,
  never at a directory that holds anything else.
- The output includes `finalfactory_BurstDebugInformation_DoNotShip`. Move the raw folder aside and
  tar-copy it into the stage without that folder (§5).
- The prepare pass leaves the project on the **Win64** target. Before you restart the editor, run
  `PrepareMacMultiplayerBuild` again in batchmode (~1 min) so Ben's editor opens on StandaloneOSX.

## 4. Verify both players
- `EntityScenes/` has `<hash>.entityheader` + `<hash>.0.entities` — not just `scene_info.bin`.
- 0 `error CS` in the Windows `build.log`; the Mac marker says `result=Succeeded errors=0`.
- A symbol added since the previous upload is present in both `FFSpaghetti.dll`
  (`honest-coop-play/scripts/symcheck.py <dll> <Symbol>`).
- File counts comparable to the previous build (diff the lists if not — a missing `_DoNotShip` file is fine).
  Diff the sizes too, and explain any big change from git before you trust it. 0.50.0.28 came out ~260 MB
  smaller (Mac 2390 MB / 537 files, Windows 2211 MB incl. DoNotShip). `25b35251f` turned off tutorial
  video transcoding (`resources.resource`), and the procedural VFX prefab rewrite shrank
  `resources.assets.resS` and the content archive. The ~2775 MB "good" reference in §2 is older.

## 5. Stage the depots like the main script
Layout the depot vdfs expect: `cicd/mp_beta_upload/mac_main/{finalfactory.app, Localization}` and
`cicd/mp_beta_upload/windows_FinalFactory/{finalfactory.exe, finalfactory_Data, …, Localization}`.
- `Localization/` = the `*.csv` files + `README.md` from repo `Localization/` — NOT
  `MissingTranslations.txt` or `FontCoverageReport.txt` (`BuildCommand2.CopyLocalizationToBuilds`).
- No folder whose name contains `DoNotShip` (`BuildCommand2.CopyDirectory`), e.g. the Windows
  player's `finalfactory_BurstDebugInformation_DoNotShip`: copy with
  `tar cf - --exclude='*DoNotShip*' --exclude='.ff*' .` from inside the player folder.
- Move the previous `cicd/mp_beta_upload` aside as `mp_beta_upload-<version>-<sha7>`; then rename the
  stage to `cicd/mp_beta_upload`.
- Update `"desc"` in `cicd/ff_app_mp_beta.vdf` (untracked) with version + sha + a few-word change list.
  Keep `"setlive" "multiplayer-closed-beta"`.

## 6. Upload (Ben signs in; see "Branch and sign-in" above)
0. **steamcmd may log in with CACHED credentials** (2026-09-25: `Logging in using cached credentials`)
   and upload at once, with no password prompt. So the stage and `"desc"` must be FINAL before you launch
   it: there may be no `password:` pause in which to swap (item 2). It then needs no sign-in from Ben.
1. Quit the Steam desktop app: `osascript -e 'quit app "Steam"'`; if it returns `User canceled (-128)`,
   `pkill -f 'MacOS/steam_osx'` (standing authorization). Verify no `steam_osx` / `Steam Helper` remains.
   Why: steamcmd and the desktop app evict each other's session (`steam-upload` skill).
2. Put the command in Ben's Terminal panel with `run_in_terminal` and open it with
   `show_pane terminal` (he may not see it otherwise):
   `steamcmd +login slims20 +run_app_build <ABS repo>/cicd/ff_app_mp_beta.vdf +quit`
   — password OFF the command line; steamcmd prompts for it, then the Steam Guard code. The agent never
   types or sees credentials.
   Swapping stages is safe while the prompt is still at `password:`, because steamcmd reads the depot
   content only after login. You can therefore swap a newer, verified stage into `cicd/mp_beta_upload`
   (atomic `mv`, old one aside, update `"desc"`) without a second login. Never swap once the login has
   gone through (2026-09-23: 0.50.0.24 replaced a staged 0.50.0.23 this way).
   **Without `run_in_terminal`:** `osascript … tell application "Terminal" to do script` from an agent
   timed out (`AppleEvent timed out (-1712)`, an unanswered Automation prompt). Instead write a
   `.command` file that runs `script -q <repo>/cicd/mp_beta_upload.log steamcmd +login slims20
   +run_app_build … +quit`, `chmod +x` it, and `open -a Terminal <file>`. `script` keeps the tty (so the
   password prompt still works) and writes a log you can read.
3. Read the tab (`read_terminal`), or the `script` log, until
   `Successfully finished AppID 1383150 build (BuildID <n>)`. With chunk dedupe, the upload took ~26 s.
   Confirm it is live: `steamcmd +login slims20 +app_info_update 1 +app_info_print 1383150 +quit` (works
   with cached credentials). `branches` → `multiplayer-closed-beta` → `buildid` must be the new BuildID,
   and each depot's `multiplayer-closed-beta` `gid` must match the `New manifestID` in
   `cicd/output_mp_beta/depot_build_*.log`.
   Tell Ben he can reopen Steam and update on the beta branch.

## 7. Record
Commit a one-line note with version, source sha and BuildID where the active work is tracked (e.g. the
active spec's `tasks.md`). Report to Ben: TL;DR (version, sha, BuildID, branch), then what was built,
verified and staged. Any new gotcha goes through `ff-agents:publish-skills` into THIS skill.
