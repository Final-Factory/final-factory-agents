---
name: two-peer-pair-lab-beast-and-m3-traps
description: "w197 (2026-10-02): running a Mac host on the M3 with a Windows client on BEAST through scripts/nightly. BEAST's sshd splits scripts in cmd.exe, kills the player with the session and has no wmic; CFFIXED_USER_HOME gives a second lab its own player data; replaying a desync report's served save as its host player; the M3 cannot hold the nightly lab plus a second build."
---

# Two-peer pair lab on the M3 and BEAST: traps (w197, 2026-10-02)

`scripts/nightly/lab.py` could not start a Windows peer on BEAST. PR #924 adds opt-in peer options
and `lab.pair-*.json`.

**BEAST over ssh.**

- sshd hands the command line to `cmd.exe`. A Git-bash script passed as `bash -lc '<script>'` is
  split at `&&` and `|` before bash sees it. Send the script over stdin:
  `ssh beast '"C:\Program Files\Git\bin\bash.exe" -l -s' < script`.
- The session's processes die when the ssh session ends, `nohup … &` or not. Keep one ssh open for
  the player's life (`exec python scripts/nightly/player_slots.py launch <player dir> -- …` as the
  last line of the stdin script: it waits, and the player runs from a firewall-allowed slot, never
  `./finalfactory.exe` in the build folder) and stop it by ending that ssh or `taskkill //PID`.
- `wmic` is gone. Find a player with PowerShell:
  `Get-CimInstance Win32_Process -Filter "Name='finalfactory.exe'"` and match its command line.
  Match on the run's own log file name, not on the scenario label, or a second run finds the first
  run's player and reads its old log as "ready".
- `AgentControl/session-*.json` holds thousands of dead files there; one process query, then the
  one file, never a query per file.
- Binary stdin through that ssh fails (`tar … | ssh` gives "Bad address"). Make a tar, `scp` it,
  unpack with a script.
- LothDesktop is a worker-root install since 2026-10-07 (w576): its player folders are
  `D:\work\ffw\players\slotK-0`/`slotK-1` per sandbox and `slotnightly-0`/`-1` for the nightly lab, picked by
  `player_slots.py` from the sandbox it runs in (`D:\work\ff-players` is gone); `python - acquire … < player_slots.py` works.

**The M3.**

- `CFFIXED_USER_HOME=<dir>` moves a Mac player's `persistentDataPath` under `<dir>/Library/…`:
  its own identity files, saves, `AgentControl` and `desyncReports`. Use it for any second lab on
  a Mac where the nightly runs, and compute the lab's data path from it.
- `arch -x86_64 <app>/Contents/MacOS/finalfactory` runs the Rosetta slice of the universal
  player, which is what Steam runs.
- A Windows player cross-builds on the Mac: `build_player.sh <clone> <sha> win <cache>`
  (WindowsStandaloneSupport is installed for 6000.3.19f1).
- An APFS copy of the lab clone (`cp -cR`, 37 s) cost about 16 GB of unshared Library blocks after
  six builds. Delete its `Library` once the last build is copied out.
- 18 GB of RAM: the nightly lab (01:30) plus a second Unity build plus four players took swap to
  10 GB and the disk to 320 MB free. One build at a time, and none while your players run.
- A build killed mid-way leaves an orphan Burst compiler (`mono … bcl`) running for hours.

**Runner traps found in w214 (2026-10-02).**

- A fresh `CFFIXED_USER_HOME` has no `Library/Application Support/Never Games/finalfactory`, and Unity then
  falls back to the legacy `com.Never-Games.finalfactory`; the runner looked in the first and reported "agent
  channel never appeared". `lab.py` now creates the folder.
- Without `--player-win-root`, `ffnightly.py run` turns every `remote-win` peer into a local Mac peer and only
  logs it. A "pre-fix Windows control" ran the Mac fix build that way. Check `Starting up in version` in each
  peer's log before counting a run.
- A scenario with a saved world and a remote Windows host needs the save in that host's own saves folder;
  `ffnightly.py` now copies it there and deletes it after.
- Rerunning under the same run tag reads the remote log the failed run left, so it fails in seconds with
  that run's status. Use a new tag.

**Replaying a desync report.** The host's report zip carries the save it served at the join
(`*_host_served-*-e1.zip`). Load it with `"world": {"saveFile": "<path>"}`. To be the saved host
player, write its reclaim GUID (the host's Player.log: `Spawning player … reclaimGuid: …`) into
`reclaim-identity-automation-host.txt` in the private data folder; the log then says
`Reusing player entity … (ReclaimByGuid …)`. `MoversDetail` kind 3 records give the players'
positions at the detail heartbeat (fp raw / 2^32); `movement.goto|x|z|tolerance|timeoutSeconds`
takes positional arguments.

**Timing.** `heartbeats` steps poll once a second, so they are ±16 heartbeats. For a timed visit
use one chain: `["ffauto:player.setposition|0|0", "ffauto:wait|1.25", "ffauto:player.setposition|-120|0"]`.
`player.setposition` works only before a client joins.

**Git.** A fresh clone's commits carry the Mac's global email and GitHub refuses the push ("email
privacy restrictions"). Set `user.email` to the noreply address the main clone uses before the
first commit.

Related: [[nightly-e2e-lab-lessons-2026-09-28]], [[fleet-harness-operational-2026-09-12]],
[[mac-player-of-a-branch-on-the-m3-lab-clone]], [[hidden-ship-stale-knn-vision-forks-host-vs-joiner]].
