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

1. **Rebuild the depots at the CURRENT HEAD.** Any staged `cicd/mp_beta_upload/` from a prior
   session is obsolete. Build the multiplayer-enabled players (editor closed for the batchmode
   build), then snapshot into `cicd/mp_beta_upload/` before uploading — the pipeline's final copy
   step deletes+rewrites `cicd/builds/`. (Build recipe: the `editor-ops` skill and the
   `unity-cli-mpdev-build-recipe` project-memory entry.)

2. **Quit the Steam desktop app.** `osascript -e 'quit app "Steam"'` may return
   `User canceled (-128)` and leave it running; if so, terminate it:
   `pkill -f 'MacOS/steam_osx'` (Ben has standing authorization to kill the project's own Steam
   desktop process to free the session — confirmed 2026-09-14). Verify nothing named `steam_osx`
   or `Steam Helper` remains. The agent CANNOT type the password or Guard code, so the actual
   `+login` with credentials is Ben's to run — hand him the exact command.

3. **Log in and upload in one command** (Ben runs this; it prompts for the password, then the
   Guard code, then uploads on that same fresh session):
   ```
   steamcmd +login slims20 <password> +run_app_build <ABS>/cicd/ff_app_mp_beta.vdf +quit
   ```
   Use an ABSOLUTE path to the vdf. Run under `nohup` if driving it through a tool with a
   background-kill timeout. Do NOT reopen the desktop app until it finishes.

4. **Verify** the BuildID in the output and confirm on the Steam partner site.

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
