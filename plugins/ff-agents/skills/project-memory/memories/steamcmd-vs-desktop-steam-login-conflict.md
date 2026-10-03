---
name: steamcmd-vs-desktop-steam-login-conflict
description: "'Why does it keep needing my login?' on the Mac Steam upload: the Steam DESKTOP app and brew steamcmd shared ~/Library/Application Support/Steam, and each desktop sign-in wiped steamcmd's cached token. FIXED 2026-09-27: steamcmd runs with HOME=/Users/benryding/.steamcmd-home, so its cached token survives and uploads need no password. Any steamcmd login still Session-Replaces the desktop app (it goes offline until Steam restarts), so do not bother quitting it first. Never store the password. M5 only."
metadata:
  type: reference
---

**Resolved 2026-09-27 (see the end of this file); the 2026-09-14 diagnosis below is history.**

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

**Current flow (Ben, 2026-09-25):** Ben signs in through the Steam app on the M5 when steamcmd prompts;
agents need no Steam password and ask Ben to sign in or approve. A branch's tester password is kept
out of this public repo.

**Not BEAST:** builds and uploads are always made on the M5 (Ben, 2026-09-25, standing rule: the M5
builds both the PC and the Mac versions). An older note here suggested uploading from BEAST; that is
retired. BEAST's desktop Steam is logged into slims20 too, so it has the same session conflict. For
unattended agents, the only open idea is giving steamcmd on the M5 its OWN writable Steam dir and
verifying that a persisted machine token (`ssfn*`) gets written before trusting a cached login.

The full build+upload recipe is the [[steam-upload]] skill. Supersedes the "Ben logs in once, then
cached" mental model in the machine-local `reference-steam-beta-branch-upload-from-mac` memory,
which was wrong about caching. Related: [[steam-desync-triage-from-the-client-side-only]],
[[unity-cli-mpdev-build-recipe]].

**Resolution (2026-09-27, tested on the M5).** The 2026-09-14 "steamcmd never caches" claim was wrong:
steamcmd DID cache a token (`Logging in using cached credentials` → OK right after Ben's sign-in), but
the next desktop-app sign-in wiped it (`Cached credentials not found`), because both used the same Steam
folder. Fix: run steamcmd with `HOME=/Users/benryding/.steamcmd-home`. Ben signed in there once, and the
cached login then worked twice with the desktop app running (offline after being replaced). Not yet observed: the token surviving a fresh desktop sign-in; expected, since the folders are now separate. Separately, every
steamcmd login makes the desktop app log off (`Session Replaced`, "not auto reconnecting") until Steam is
restarted. That is why quitting the desktop app first no longer helps. Recipe: [[steam-upload]], [[mp-beta-deploy]] §6.
