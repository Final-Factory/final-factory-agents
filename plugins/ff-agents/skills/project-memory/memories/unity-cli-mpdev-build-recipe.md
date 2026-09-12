---
name: unity-cli-mpdev-build-recipe
description: "Building the multiplayer-dev players from the unity CLI shim without the bridge: the shim takes the subcommand name directly (no --json flag; run_tests filter_type is testName|assembly|category); call the private BuildAllMultiplayerDevNoUpload by reflection inside a guarded EditorApplication.update callback with a marker file (it runs the localization harvest, fonts, both platforms, the Localization copy and the cicd copy, unlike BuildWindows/OsxMultiplayerDev alone); the no-version-update path never writes PlayerSettings.bundleVersion (set it by eval first or the plist/Info stays stale); a run that triggers a platform switch can reimport every shader graph and take ~140 min instead of 24; never git rebase --autostash while a build is running with uncommitted build inputs."
---

# Multiplayer-dev player builds from the `unity` CLI shim (2026-09-12, 069 depot rebuild)

- **Shim syntax** (`~/.local/bin/unity`, `scripts/unity-cli.sh`): `unity editor_status --project-path <repo>`,
  `unity command --project-path <repo> <name> [key=value…]`, `unity eval '<C# statements; return x;>'
  --project-path <repo>`. There is NO `--json` flag — passing it silently prints nothing.
  `run_tests` accepts `filter_type=testName|assembly|category` (not namespace) — but a testName filter did NOT
  narrow the run, and `Temp/pipeline_test_status.json` can be STALE: parse the shim's own JSON
  (`result.Summary`, `result.Results[].Status`) — see [[unity-shim-run-tests-filter-does-not-narrow-and-static-test-isolation]].
- **Full pipeline, not the platform entry points.** `Editor.BuildCommand2.BuildWindowsMultiplayerDev()` /
  `BuildOsxMultiplayerDev()` build one player each and SKIP the localization harvest + font check, the
  `Localization/` copy into each build and the `cicd/builds/{windows/main/FinalFactory,mac/main}` copy.
  For a Steam depot use the menu path: `typeof(Editor.BuildCommand2).GetMethod("BuildAllMultiplayerDevNoUpload",
  NonPublic|Static).Invoke(null,null)` inside a one-shot guarded `EditorApplication.update` callback that
  writes a marker file (`running` → `returned last=<result> errors=<n> bundleVersion=<v>` / `failed: <ex>`),
  scheduled through `unity command … eval_file file=<path.cs>`; the CLI call returns immediately.
  Refuse to schedule while playing/compiling, and guard against double scheduling with a second file.
- **bundleVersion is not set on the no-version-update path** (`BuildAndUploadAllInternal`, only the
  `updateVersion` branch writes `PlayerSettings.bundleVersion`), so the built app's Info.plist stays at the OLD
  version while `FFVersion.FinalFactoryVersion` (what the join gate and `hello.gameVersion` use) is the new
  one. Set it first: `unity eval 'UnityEditor.PlayerSettings.bundleVersion = "0.50.0.16";
  UnityEditor.AssetDatabase.SaveAssets(); …'`. Loth's version-bump commits touch FFVersion.cs +
  ProjectSettings bundleVersion + the four canonical depot vdfs' manifest ids (those come from Steam after upload).
- **Duration.** Build #1 (Windows then macOS) took 24 min; build #2 with the same code + a 1-line change took
  ~138 min because the macOS leg reimported every shader graph. Arm the marker monitor for ≥60 min and re-arm;
  the editor's Pipeline HTTP server is unreachable during the build (`Main thread operation timed out`), so
  `editor_status` hanging is not a wedge — judge progress by `Editor.log` growth and build-folder mtimes.
- **Never `git rebase --autostash` while a build is running with uncommitted build inputs** (FFVersion.cs,
  ProjectSettings.asset): the stash momentarily reverts them under the editor. Commit the plan file and push
  fast-forward, or wait for the marker.
- Related: [[steam-beta-branch-upload-from-mac]], [[editor-via-unity-cli-when-the-bridge-is-down]].
