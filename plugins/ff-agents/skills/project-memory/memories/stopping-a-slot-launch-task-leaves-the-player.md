# Stopping a slot launch's background task leaves the player running (Windows)

**What happened (w3051, 2026-11-04, LothDesktop, a pair run's client leg).** The client player ran as a Claude Code
background Bash task: `timeout -s TERM 3000 python scripts/nightly/player_slots.py launch --peer 1 <exe> -- ...`.
Stopping that task (TaskStop) ended the shell, `timeout` and the Python wrapper, but `finalfactory.exe` kept running,
both times it was tried. `ff-leftovers list` and `ff-leftovers end` then said "Nothing your session started is still
running" while the player was up, so neither the task stop nor the leftover check ends it.

**How to end it.** Read the player's command line first, then stop it by pid only when it is yours (your slot folder
and your `$TMPDIR` log path):

```powershell
$p = Get-CimInstance Win32_Process -Filter "ProcessId=<pid>"; $p.CommandLine
if ($p.CommandLine -like '*slot3-1*<your ffa- folder>*') { Stop-Process -Id <pid> -Force }
```

The pid comes from `python scripts/nightly/player_slots.py mine --one` or `scripts/agent/peer.py <log folder> list`.
Check `tasklist` afterwards, and before DONE.

**Also from that leg (built Windows player, driven by `scripts/agent/peer.py`):**
- Launch it with `-ffAgentControl true` (drive-game SKILL.md, "agent channel"); a pair-run brief that says "no
  switches" means no test switches, and without this one peer.py cannot move it, read state or take stills. The
  first client run of w3051 had to quit and rejoin for it.
- Set `PYTHONIOENCODING=utf-8` before peer.py on Windows: `v1/help` holds characters cp1252 cannot print.
- State is `v1/snapshot/<scope>` (player, inventory, nearby, enemies, tasks, research, objectives, alerts, session,
  structure, chat, minimap); a building is `ffauto:observe.state|structure|<x>|<z>`; `ffauto:players.dump` counts the
  players in play. A Steam lobby join at launch is `+connect_lobby <lobby id>`.
