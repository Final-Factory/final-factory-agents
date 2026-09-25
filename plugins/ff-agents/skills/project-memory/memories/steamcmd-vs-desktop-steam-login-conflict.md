---
name: steamcmd-vs-desktop-steam-login-conflict
description: "'Why does it keep needing my login, I keep logging in!' on the Mac Steam upload — it is NOT a bad password: the Steam DESKTOP app and brew steamcmd share one account (slims20) and one data folder, Steam allows one live session per account so they evict each other, AND a fresh steamcmd login reports 'Cached credentials not found' regardless of desktop state. Logging into the desktop app never helps steamcmd. Fix: quit the desktop app, then log in AND upload in ONE steamcmd command; on the M5 only (Ben 2026-09-25: all builds and uploads come from the M5, never BEAST)."
metadata:
  type: reference
---

Diagnosed 2026-09-14 (Ben, frustrated that repeated logins never stuck).

**Symptom:** every Steam upload handoff says "needs Ben's steamcmd login," Ben logs in again, and the
next upload still asks. The login was never the blocker.

**Root cause (path-traced this session):**
- Two programs use the SAME account `slims20`: the Steam **desktop app**
  (`~/Library/Application Support/Steam/Steam.AppBundle/.../steam_osx`, seen running as PID 88121)
  and **`steamcmd`** (brew, `/opt/homebrew/bin/steamcmd` → `/opt/homebrew/Caskroom/steamcmd/.../MacOS`),
  which is what does the upload. On the Mac they share the `~/Library/Application Support/Steam` data.
- Steam permits ONE live session per account. `connection_log.txt` showed the desktop client
  re-logging on every ~16 min and a `[Logged Off] ... "we don't have a valid username/password or
  token set yet"` — the two clients rotating/evicting the shared session token.
- Decisive probe: with the desktop app CLOSED, `steamcmd +login slims20 +quit` (stdin closed) still
  printed **"Cached credentials not found."** then prompted for a password. So steamcmd does NOT
  read the desktop app's login and does NOT persist its own token between runs on this Mac. Its
  Caskroom `config/` stays empty; the desktop `loginusers.vdf` (RememberPassword=1) is the app's, not
  steamcmd's.
- Steam Guard 2FA compounds it: a non-interactive `+login slims20 +quit` cannot supply a code, so
  even a would-be cached run fails and reads as "needs login again."

**What works:** quit the desktop Steam app first (`pkill -f 'MacOS/steam_osx'` — `osascript quit`
can return `User canceled (-128)` and leave it running; Ben authorized killing the project's own
Steam desktop process to free the session), then log in AND upload in ONE command, entering the
password + Guard code at that moment:
`steamcmd +login slims20 <password> +run_app_build <ABS>/cicd/ff_app_mp_beta.vdf +quit`.
Do NOT rely on a cached login carrying over between runs on the Mac. The agent cannot type the
password/Guard, so the credentialed `+login` is Ben's to run — hand him the exact command.

**Not BEAST:** builds and uploads are always made on the M5 (Ben, 2026-09-25, standing rule: the M5
builds both the PC and the Mac versions). An older note here suggested uploading from BEAST; that is
retired. BEAST's desktop Steam is logged into slims20 too, so it has the same session conflict. For
unattended agents, the only open idea is giving steamcmd on the M5 its OWN writable Steam dir and
verifying that a persisted machine token (`ssfn*`) gets written before trusting a cached login.

The full build+upload recipe is the [[steam-upload]] skill. Supersedes the "Ben logs in once, then
cached" mental model in the machine-local `reference-steam-beta-branch-upload-from-mac` memory,
which was wrong about caching. Related: [[steam-desync-triage-from-the-client-side-only]],
[[unity-cli-mpdev-build-recipe]].
