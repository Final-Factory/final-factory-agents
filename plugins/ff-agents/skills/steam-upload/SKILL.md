---
name: steam-upload
description: Upload a multiplayer build to the password-protected Steam multiplayer-closed-beta branch from the M5 Mac with steamcmd — the Steam login/upload mechanics that mp-beta-deploy (the fallback when ffbox cannot make the beta build) relies on. NOT for releases: a release (main or demo, any version on master/develop) goes through CI on ffbox via ci-release, never a manual upload. Carries the login recipe that actually works — steamcmd runs with its own HOME and reuses a cached token; the "it keeps asking me to log in" problem was the desktop app wiping steamcmd's token in the shared Steam folder, not a bad password.
---

# Uploading a Final Factory build to Steam (from the Mac)

**Releases never come through here.** Every release build of the main game and the demo is built
and uploaded by CI on the ffbox build server: use the `ci-release` skill. Nobody builds or uploads
a release by hand any more (no `Build and Upload All`, no steamcmd, no ZIP upload). This skill
covers only the MP closed-beta upload (`mp-beta-deploy`).

**Which build skill, in one line:** a new closed-beta build is a develop `ci-release` (ffbox sets its
main app live on `multiplayer-closed-beta`, 2026-09-26); a public release is a master `ci-release`;
`mp-beta-deploy` (this skill's upload mechanics) is only the fallback when ffbox is down or for a
special build. Full decision table: project-memory `which-build-skill`.

**Branch and sign-in (Ben, 2026-09-25, supersedes older notes below where they differ):** the MP beta
branch is **`multiplayer-closed-beta`**, never `development` (another branch on the same app). Uploads use
steamcmd on the M5 with its own home and a cached token (below), so normally nobody signs in. When the
token is rejected, steamcmd prompts and Ben signs in; agents need no Steam password and never ask for one. The branch's tester password (for
`app_update 1383150 -beta multiplayer-closed-beta -betapassword <pw>` to install or verify the build as
a tester) is deliberately NOT in this public repo: it is in the private game repo, 068 `tasks.md` T041,
or ask Ben.

## The login model that actually works — read this FIRST (proven 2026-09-27)

**steamcmd on the M5 runs with its own home: `HOME=/Users/benryding/.steamcmd-home`.** It then keeps its
own Steam folder (`$HOME/Library/Application Support/Steam`), and the token from Ben's last sign-in is
reused: `Logging in using cached credentials` → `OK`, with no password and no Steam Guard.

Why the own home: with the default home, steamcmd and the Steam **desktop app** share
`~/Library/Application Support/Steam`. steamcmd did cache a token (a login right after Ben's sign-in
used it), but the next time the desktop app signed in, steamcmd said **"Cached credentials not found"**.
That is the "it keeps asking me to log in" problem, and it is not a bad password.

What still conflicts: Steam allows one session per account. **Any steamcmd login replaces the desktop
app's session** (`connection_log.txt`: `RecvMsgClientLoggedOff('Session Replaced')`, then "not auto
reconnecting"). The desktop app goes offline, and a game running from it loses Steam, until Ben restarts
Steam. Quitting the desktop app first no longer buys anything, so **do not quit it**; warn Ben if he is
playing, and tell him to restart Steam afterwards.

Rules: always `+login slims20` with **no password argument**. Never store the password in a file,
script, env var or keychain. Only when steamcmd prints `Cached credentials not found` (token rejected
or expired) does Ben type the password and approve Steam Guard, at steamcmd's own prompt.

## Recipe

1. **Building + deploying the MP beta is its own skill: `ff-agents:mp-beta-deploy`** (Ben's word only).
   It carries the full verified procedure. This skill is the Steam login/upload mechanics it relies on.
   Never use the Build menu for the beta: every Build path strips the multiplayer define (`6c8dc3f99`).

2. **Test the token:** `HOME=/Users/benryding/.steamcmd-home steamcmd +login slims20 +quit < /dev/null`.
   `...OK` means no sign-in is needed. Without a tty a missing token fails once (`Invalid Password`)
   instead of hanging.

3. **Upload from a Terminal window** (so a `password:` prompt can still reach Ben if the token was rejected):
   a `.command` file with `export HOME=/Users/benryding/.steamcmd-home` and
   `script -q <repo>/cicd/mp_beta_upload.log steamcmd +login slims20 +run_app_build <ABS>/cicd/ff_app_mp_beta.vdf +quit`,
   then `open -a Terminal <file>`. Use an ABSOLUTE path to the vdf. If it stops at `password:`, ask Ben
   to sign in there. A wrong password makes steamcmd exit: relaunch the same file.

4. **Verify** the BuildID in the output, then `app_info_print 1383150` with the same `HOME` (see
   `mp-beta-deploy` §6).

**First-time setup on a new home** (done on the M5 2026-09-27): `mkdir -p ~/.steamcmd-home`, then run
`HOME=~/.steamcmd-home steamcmd +login slims20 +quit` in a Terminal window for Ben to sign in once.

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

## Beta builds and uploads come from the M5, never BEAST

Standing rule (Ben, 2026-09-25): every MP beta build is made on the M5, because it builds both the
PC and the Mac versions, and the upload runs there too. (Releases are built on ffbox: `ci-release`.) Do not build or upload from BEAST,
even though BEAST has a steamcmd (`C:\steamworks\sdk	ools\ContentBuilderuilder`) with a cached
`slims20` entry: its desktop Steam is logged into the same account and the live play clients there use
that session, so a steamcmd login on BEAST can knock them off. A Windows-only upload would also leave
the branch's Mac depot out of step with the Windows one.

Related project-memory: `steamcmd-vs-desktop-steam-login-conflict`,
`steam-desync-triage-from-the-client-side-only`, `unity-cli-mpdev-build-recipe`.
