---
name: steam-upload
description: Build and upload a Final Factory build to Steam from this Mac (the password-protected multiplayer-closed-beta branch, or a normal depot) with steamcmd. Use when asked to upload to Steam, push a depot, or ship a build to the beta branch. Carries the login recipe that actually works — the "it keeps asking me to log in" problem is a desktop-Steam-vs-steamcmd session conflict, not a bad password.
---

# Uploading a Final Factory build to Steam (from the Mac)

**Branch and sign-in (Ben, 2026-09-25, supersedes older notes below where they differ):** the MP beta
branch is **`multiplayer-closed-beta`**, never `development` (another branch on the same app). Uploads use
steamcmd on the M5, and Ben signs in through the Steam app on the M5 when steamcmd prompts, so agents
need no Steam password and never ask for one: when steamcmd wants a sign-in or approval, stop and ask
Ben to sign in or approve it, then carry on. The branch's tester password (for
`app_update 1383150 -beta multiplayer-closed-beta -betapassword <pw>` to install or verify the build as
a tester) is deliberately NOT in this public repo: it is in the private game repo, 068 `tasks.md` T041,
or ask Ben.

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

1. **Building + deploying the MP beta is its own skill: `ff-agents:mp-beta-deploy`** (Ben's word only).
   It carries the full verified procedure. This skill is the Steam login/upload mechanics it relies on.
   Never use the Build menu for the beta: every Build path strips the multiplayer define (`6c8dc3f99`).

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

## Builds and uploads come from the M5, never BEAST

Standing rule (Ben, 2026-09-25): every build that goes to Steam is made on the M5, because it builds
both the PC and the Mac versions, and the upload runs there too. Do not build or upload from BEAST,
even though BEAST has a steamcmd (`C:\steamworks\sdk	ools\ContentBuilderuilder`) with a cached
`slims20` entry: its desktop Steam is logged into the same account and the live play clients there use
that session, so a steamcmd login on BEAST can knock them off. A Windows-only upload would also leave
the branch's Mac depot out of step with the Windows one.

## If you want unattended agent uploads

The "log in once, cache, agents upload later" model does NOT hold on the Mac (see above). To make
it work you must give steamcmd its OWN writable Steam dir (dedicated install/HOME), log in there
once, and VERIFY it actually wrote a persisted machine token (`ssfn*` / `config/config.vdf`) —
then always upload from that dir with the desktop app never using the same account. Until that is
set up and verified, treat every upload as an interactive login+upload in one command.

Related project-memory: `steamcmd-vs-desktop-steam-login-conflict`,
`steam-desync-triage-from-the-client-side-only`, `unity-cli-mpdev-build-recipe`.
