---
name: mp-beta-deploy
description: Build the multiplayer-enabled Mac + Windows players from develop and deploy them to the password-protected Steam `multiplayer-closed-beta` branch for Ben and his testers — the full verified procedure (pre-steps, both builds, verification, depot staging, Steam upload, record). Use when Ben asks for it in any words — "push a new beta build", "deploy to the MP beta", "make a build Kyle and I can test", "upload to the beta branch". Never start it on your own initiative or as a side step of other work.
---

# Deploy a build to the MP beta branch

**Only when Ben asks** (plain English is enough — he never has to type the skill name). This publishes
a build that other people download, so never start it on your own initiative; if you think one is
needed, say so and wait for him to ask. Proven end to end on 2026-09-23 (0.50.0.21, develop `f594db63d`, BuildID 25471784).

**Both players are built on the M5, never on BEAST** (Ben, 2026-09-25, standing rule): the M5
builds both the PC and the Mac versions, so every release or upload build (this beta branch, the
default branch, any Steam branch) comes from it. Do not build an upload player on BEAST or in an
ffsb sandbox, even when the M5 is busy: wait for it, or ask Ben. BEAST sandboxes still build
test-leg and play-client players (`honest-coop-play`), which are never uploaded.

**Why this is not the Build menu:** every `Build` menu path strips `FF_ENABLE_MULTIPLAYER_BUILD`
(`BuildCommand2.StripMultiplayerBuildDefine`, since `6c8dc3f99`), so "Build and Upload All" produces a
build with multiplayer HIDDEN — and its upload goes to the DEFAULT branch. Never use it for this. The
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
4. **The bridge can RE-DISPATCH a timed-out call B.** The same day, a second `BuildPlayer` started 27 s after
   the first returned (16:15:47 vs 16:15:20 UTC) and wrote a fresh stage dir. Never assume only one build
   ran. The marker can hold several start/`returned` pairs, or reappear after you move the stage aside.
   Before you stage anything, confirm that every file in the stage has an mtime from the build you trust
   (`find <app> -newermt '<local start time>' -type f | wc -l` equals the file count; `-newermt` is LOCAL
   time).

## 3. Windows player (on the M5)
Build it on the M5 from the same source sha as the Mac player (rule above). The repo's entry points are
`Editor.LocalMultiplayerVerificationBuild.PrepareWindowsMultiplayerBuild` and then
`BuildWindowsMultiplayerDev` with `-ffVerificationBuildOutput <stage>/windows_FinalFactory/finalfactory.exe`
(`Assets/Editor/LocalMultiplayerVerificationBuild.cs`), as two SEPARATE batchmode sessions with the editor
closed. The prepare pass switches the active target and adds `FF_ENABLE_MULTIPLAYER_BUILD` to
`ProjectSettings.asset`; never commit that edit. Wait on a status file (`prepare rc=`, `build rc=`, `done`),
never on the bridge. The Windows leg has not yet been run on the M5 (before 2026-09-25 it ran on BEAST,
which is retired for upload builds): record its first run's gotchas here.

## 4. Verify both players
- `EntityScenes/` has `<hash>.entityheader` + `<hash>.0.entities` — not just `scene_info.bin`.
- 0 `error CS` in the Windows `build.log`; the Mac marker says `result=Succeeded errors=0`.
- A symbol added since the previous upload is present in both `FFSpaghetti.dll`
  (`honest-coop-play/scripts/symcheck.py <dll> <Symbol>`).
- File counts comparable to the previous build (diff the lists if not — a missing `_DoNotShip` file is fine).

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

## 6. Upload (Ben types the credentials)
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
3. Read the tab (`read_terminal`) until `Successfully finished AppID 1383150 build (BuildID <n>)`.
   Tell Ben he can reopen Steam and update on the beta branch.

## 7. Record
Commit a one-line note with version, source sha and BuildID where the active work is tracked (e.g. the
active spec's `tasks.md`). Report to Ben: TL;DR (version, sha, BuildID, branch), then what was built,
verified and staged. Any new gotcha goes through `ff-agents:publish-skills` into THIS skill.
