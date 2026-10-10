---
name: two-built-players-on-one-machine-share-port-7777
description: "Built players launched with -ffAutomationRole host from two sandboxes on one machine both want automation port 7777: the second never starts its world and sits at state 'menu' with no error; give each its own -ffAutomationPort and -logFile, and stop only your own player by pid."
---

# Two built players on one machine share automation port 7777 (2026-10-09, w809)

**Symptom.** A player launched through the slot pool with `-ffAgentControl true -ffAutomationRole host ...`
answers `/v1/hello` but stays at `"state": "menu"`, heartbeat 0, for as long as you wait; its log says the
host could not listen. Another sandbox's player (a different build, same machine) held port 7777, the default.

**Do.** Pass `-ffAutomationPort <your own>` (w809 used 7803, and 7863 inside `run_railgun_audit.sh`) and
`-logFile <a file in your temp folder>` so your log is not the shared `Player.log`. Find the agent channel by pid:
`AgentControl/session-<pid>.json`, not "the newest file". List players with
`Get-CimInstance Win32_Process -Filter "Name='finalfactory.exe'"` and read the label and port off the command line;
stop only your own pid (`taskkill /PID`); the hook refuses killing Unity, node, claude and PowerShell by hand.

**Clips.** `record_clip` (ddagrab) produced no frames on lothdesktop (a 0-byte file); the fallback is the player's
own frame capture, `-ffFeelProbe <csv> -ffFeelFrames <dir> -ffFeelFramesAt <start>+<seconds> -ffFeelFramesWidth 1280
-ffFeelVsync 0 -ffFeelFps 60`, assembled by `frames.csv` times (see `beast-clip-capture-and-slot-launch-traps`). The
capture cost the game 41 distinct frames a second at 1280 wide against 130-180 fps uncaptured, so `watch_video`
flags STUTTER; say so in the PR rather than call the clip 60 fps.
