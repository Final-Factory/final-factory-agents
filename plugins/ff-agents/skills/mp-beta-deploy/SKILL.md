---
name: mp-beta-deploy
description: Build the multiplayer-enabled Mac + Windows players from develop and deploy them to the password-protected Steam `multiplayer-closed-beta` branch for Ben and his testers — the full verified procedure (pre-steps, both builds, verification, depot staging, Steam upload, record). Use when Ben asks for it in any words — "push a new beta build", "deploy to the MP beta", "make a build Kyle and I can test", "upload to the beta branch". Never start it on your own initiative or as a side step of other work.
---

# Deploy a build to the MP beta branch

**Only when Ben asks** (plain English is enough — he never has to type the skill name). This publishes
a build that other people download, so never start it on your own initiative; if you think one is
needed, say so and wait for him to ask. Proven end to end on 2026-09-23 (0.50.0.21, develop `f594db63d`, BuildID 25471784).

**Why this is not the Build menu:** every `Build` menu path strips `FF_ENABLE_MULTIPLAYER_BUILD`
(`BuildCommand2.StripMultiplayerBuildDefine`, since `6c8dc3f99`), so "Build and Upload All" produces a
build with multiplayer HIDDEN — and its upload goes to the DEFAULT branch. Never use it for this. The
repo's documented multiplayer build path is `Editor.LocalMultiplayerVerificationBuild` (README
"Multiplayer Menu Visibility"). It skips the main script's extras, so this skill runs them by hand to
match `BuildCommand2.BuildAndUploadAllInternal`. No other shortcuts ("no hacks" — Ben).

## 0. Preconditions
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

## 3. Windows player (on BEAST)
`ssh -o Hostname=10.0.0.158 beast`; Git bash `"C:\Program Files\Git\bin\bash.exe" -lc` cannot carry `|`
— scp a script and run it. Checkout `/c/Users/rydin/nevergames/FinalFactory`, lab
`C:/Users/rydin/ff-worker`.
1. `git bundle create <lab>/t<N>-source.bundle <beast-HEAD>..<temp-branch-at-sha>` (a bundle needs a
   named ref; delete the temp branch after) and `git bundle verify`.
2. Copy the newest `$E/sync-build-t<N>-beast.sh` + `build-win-t<N>.sh` (honest-coop-play lab
   `E=/Users/benryding/nevergames/ff-audit-artifacts/074-20260921`) to the next tag with `sed`; they
   fast-forward the checkout to the sha, refuse an existing output, check free space, then run
   `PrepareWindowsMultiplayerBuild` and `BuildWindowsMultiplayerDev` in two batchmode sessions.
3. scp bundle + scripts to the lab; launch DETACHED:
   `(ssh -n … '"…bash.exe" -lc "bash …/sync-build-t<N>-beast.sh …/t<N>-source.bundle <sha40>"' > out 2>&1 &)`.
   Wait for the ssh process to exit, then read `build-t<N>/build-status.txt` (`prepare rc=0`, `build rc=0`, `done`).

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
- No folder whose name contains `DoNotShip` (`BuildCommand2.CopyDirectory`). For Windows: on BEAST
  `tar cf … --exclude='*DoNotShip*' --exclude='.ff*' .` inside `build-t<N>/player`, scp, unpack.
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
3. Read the tab (`read_terminal`) until `Successfully finished AppID 1383150 build (BuildID <n>)`.
   Tell Ben he can reopen Steam and update on the beta branch.

## 7. Record
Commit a one-line note with version, source sha and BuildID where the active work is tracked (e.g. the
active spec's `tasks.md`). Report to Ben: TL;DR (version, sha, BuildID, branch), then what was built,
verified and staged. Any new gotcha goes through `ff-agents:publish-skills` into THIS skill.
