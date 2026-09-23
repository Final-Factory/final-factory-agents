---
name: steam-upload
description: Build and upload a Final Factory build to Steam from this Mac (the password-protected multiplayer-closed-beta branch, or a normal depot) with steamcmd. Use when asked to upload to Steam, push a depot, or ship a build to the beta branch. Carries the login recipe that actually works — the "it keeps asking me to log in" problem is a desktop-Steam-vs-steamcmd session conflict, not a bad password.
---

# Uploading a Final Factory build to Steam (from the Mac)

## The login model that actually works — read this FIRST

The recurring "why does it keep needing my login, I keep logging in!" is NOT a bad password and
NOT a login that fails to save. It is TWO different Steam programs fighting over one account:

- the **Steam desktop app** (`~/Library/Application Support/Steam/.../steam_osx`), and
- **`steamcmd`** (brew: `/opt/homebrew/bin/steamcmd` → a Caskroom root), which is what uploads.

Both use the same account (`slims20`) and, on the Mac, the same data folder. Steam allows only one
live session per account, so they evict each other. Worse (proven 2026-09-14): a fresh
`steamcmd +login slims20 +quit` reports **"Cached credentials not found"** even with the desktop
app closed — steamcmd does NOT read the desktop app's login, and its own token does not persist
between runs on this Mac. So:

- **Logging into the Steam desktop app never helps steamcmd.** Stop expecting a cached login to
  carry over.
- **A non-interactive `steamcmd +login slims20 +quit` cannot succeed** — no cached token, and
  Steam Guard has no way to supply a 2FA code. It fails and looks like "needs login again."

**Therefore: quit the desktop app, then log in AND upload in ONE steamcmd command**, supplying the
password and the Steam Guard code at that moment. Do not rely on caching.

## Recipe

1. **Build the multiplayer depots at the CURRENT HEAD** — the full recipe is the section
   "Building the MP beta depots" below. Every `Build` menu path STRIPS the multiplayer define
   (`BuildCommand2.StripMultiplayerBuildDefine`, since `6c8dc3f99`), so "Build and Upload All" makes a
   build with multiplayer HIDDEN — never use it for the beta, and never its upload (that is the
   default branch). Any staged `cicd/mp_beta_upload/` from a prior session is obsolete.

2. **Quit the Steam desktop app.** `osascript -e 'quit app "Steam"'` may return
   `User canceled (-128)` and leave it running; if so, terminate it:
   `pkill -f 'MacOS/steam_osx'` (Ben has standing authorization to kill the project's own Steam
   desktop process to free the session — confirmed 2026-09-14). Verify nothing named `steam_osx`
   or `Steam Helper` remains. The agent CANNOT type the password or Guard code, so the actual
   `+login` with credentials is Ben's to run — hand him the exact command.

3. **Log in and upload in one command** (Ben runs this; it prompts for the password, then the
   Guard code, then uploads on that same fresh session):
   ```
   steamcmd +login slims20 +run_app_build <ABS>/cicd/ff_app_mp_beta.vdf +quit
   ```
   Leave the password OFF the command line — steamcmd prompts for it (and then the Guard code), so it
   never lands in shell history. In the Claude desktop app, type the command into Ben's Terminal panel
   with `run_in_terminal` and open the panel (`show_pane terminal`) so he sees the `password:` prompt.
   Use an ABSOLUTE path to the vdf. Do NOT reopen the desktop app until it prints the BuildID.

4. **Verify** the BuildID in the output and confirm on the Steam partner site.

## Building the MP beta depots (verified 2026-09-23, BuildID 25471784)

The documented multiplayer build path is `Editor.LocalMultiplayerVerificationBuild` (README "Multiplayer
Menu Visibility"): Development players with `FF_ENABLE_MULTIPLAYER_BUILD`. It skips the main script's
extras, so run those by hand to match `BuildCommand2.BuildAndUploadAllInternal`:

1. **Pre-steps (in the editor, not playing):** `Editor.Localizer.HarvestAndExport()`, then
   `Editor.FontCoverage.RebuildFontAtlases()`, then `Editor.FontCoverage.ValidateFontCoverageOrThrow()`.
   Commit whatever they change (e.g. rebaked CJK font atlases) BEFORE building, so the build source
   is a pushed commit.
2. **Mac player, in the editor** (define set + target StandaloneOSX, or run the verification Prepare pass
   first): force-reimport `Assets/Scenes/main/EntitySubScene.unity` in ONE `execute_code` call, then
   `BuildPipeline.BuildPlayer` (Development, enabled scenes) into a fresh staging folder in a SEPARATE
   call, writing a marker file (the bridge times out before the build ends). In one call the build
   races the entity bake and ships only `scene_info.bin`.
3. **Windows player, on BEAST**: `git bundle` the new commits (a bundle needs a named ref — make a
   temporary branch at the sha), fast-forward BEAST's checkout, run the `build-win-<tag>.sh` pattern
   (`PrepareWindowsMultiplayerBuild` then `BuildWindowsMultiplayerDev` in two batchmode sessions; the lab
   copies live in the honest-coop-play `$E` as `sync-build-<tag>-beast.sh` / `build-win-<tag>.sh`).
   Launch it detached.
4. **Verify both**: `EntityScenes/` has `.entityheader` + `.0.entities` (not just `scene_info.bin`);
   0 `error CS` in the build log; a symbol added since the previous upload is present in
   `FFSpaghetti.dll` (`honest-coop-play/scripts/symcheck.py`).
5. **Stage like the main script**: `cicd/mp_beta_upload/mac_main/{finalfactory.app, Localization}` and
   `cicd/mp_beta_upload/windows_FinalFactory/{…, Localization}`. `Localization` = the `*.csv` files +
   `README.md` from `Localization/` (NOT `MissingTranslations.txt`, `BuildCommand2.cs:612-660`). Drop any
   folder whose name contains `DoNotShip` (`BuildCommand2.cs:721`) — for the Windows player, tar it on
   BEAST with `--exclude='*DoNotShip*'` and unpack locally. Keep the previous snapshot as
   `mp_beta_upload-<version>-<sha>` rather than deleting it.
6. Update `desc` in `cicd/ff_app_mp_beta.vdf` (untracked) with version + sha, then the upload steps above.

Known cosmetic drift: the Mac Info.plist takes `PlayerSettings.bundleVersion`, which can lag
`FFVersion.FinalFactoryVersion` (the version the game shows and the join gate compares).

## Facts and gotchas

- The three `*_mp_beta.vdf` in `cicd/` are UNTRACKED and carry `setlive multiplayer-closed-beta`
  with forward-slash contentroots pointing at the `cicd/mp_beta_upload/` snapshot. The canonical
  depot vdfs are left untouched.
- The **in-editor uploader is Windows-only** (`FindSteamCmdPath` wants `steamcmd.exe`,
  `BuildCommand2.cs`), so the Mac path is always `steamcmd` on the command line.
- **`cicd/credentials.txt` is stale/misleading** ("Invalid Password"; username `slims` vs the real
  `slims20`). Ignore it.
- **Mac Addressables/shader build fails with `SBP ErrorError`** if Xcode's Metal Toolchain is
  missing (`cannot execute tool 'metal'` in Editor.log). Fix:
  `xcodebuild -downloadComponent MetalToolchain` (~690 MB).
- **Never fire a >timeout editor build via `execute_menu_item`**: the bridge re-dispatches the
  timed-out command on every reconnect (each build's domain reload) and it runs several times.
  Use a batchmode route or an idempotent guarded wrapper.
- The **branch and its password are created by Ben in the Steam partner UI** — there is no API for
  branch creation or passwords.

## The reliable alternative: upload from BEAST (Windows)

BEAST has no competing desktop Steam client, so the session conflict does not arise there. The
notes say uploads "normally" live on the Windows box for exactly this reason. If the Mac login
keeps fighting, build + upload from BEAST instead.

## If you want unattended agent uploads

The "log in once, cache, agents upload later" model does NOT hold on the Mac (see above). To make
it work you must give steamcmd its OWN writable Steam dir (dedicated install/HOME), log in there
once, and VERIFY it actually wrote a persisted machine token (`ssfn*` / `config/config.vdf`) —
then always upload from that dir with the desktop app never using the same account. Until that is
set up and verified, treat every upload as an interactive login+upload in one command.

Related project-memory: `steamcmd-vs-desktop-steam-login-conflict`,
`steam-desync-triage-from-the-client-side-only`, `unity-cli-mpdev-build-recipe`.
