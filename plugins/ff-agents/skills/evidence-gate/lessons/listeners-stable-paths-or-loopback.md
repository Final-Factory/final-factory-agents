---
name: listeners-stable-paths-or-loopback
description: "Windows Firewall asks once for every new program path that listens beyond loopback, and the prompt covers an unattended machine's desktop and every clip taken under it (w1742). Anything you start that listens binds 127.0.0.1; node comes from PATH (the worker root's tools\\node), never a copy unpacked into $TMPDIR; a built player runs only from its slot (player_slots.py), and `player_slots.py firewall` says when a slot's rule is missing. Before you publish a clip or still, look at a frame of each for a system dialog (firewall, UAC, crash) over the game."
date: 2026-10-22
---

# Listeners start from a stable path or bind loopback; a clip is checked for system dialogs (w1742)

**Rule.** Windows Firewall shows an "allow access" prompt the first time a program path listens on any address but
loopback (0.0.0.0, `::`, or no host given, which is the default for node's `listen(port)` and Python's
`bind(("", port))`). A listen on 127.0.0.1 never prompts. A path that has a rule (allow or block) never prompts. So:

- **Bind what you start to 127.0.0.1**: a test server, a mock, a probe, a dev server (`--host 127.0.0.1`). Nothing off
  the machine has to reach it. A port check binds loopback and finds a wildcard holder some other way (connect to it;
  on Windows a loopback bind succeeds beside a socket on 0.0.0.0 of the same port, measured).
- **Never unpack a runtime into `$TMPDIR` and run it.** Each session's temp folder is a new path, and so a new prompt.
  On a Windows worker, node 24 is on PATH from the root's `tools\node` (ff-factory `server/agentNode.ts`); if it is
  missing or too old, say so in the report, do not download one.
- **A built player runs only from its slot** (`player_slots.py launch`, `FF_LAUNCH`). A launch that warns
  `no inbound firewall rule names ...`, or a prompt over a slot player, means that machine's install lacks the rule:
  run `python scripts/nightly/player_slots.py firewall`, put its output in the report, and have the orchestrator send
  the ops worker (an elevated rerun of the install). Never ask a person to click the prompt.
- **Look at a frame of every clip and still before you publish it.** A firewall prompt, UAC, a crash dialog or a
  "not responding" box drawn over the game voids the capture: re-take it once the dialog is gone.

**Why.** lothsahn, 2026-10-22: "We made a bunch of static slots to fix the windows firewall which has solved it there,
but now we're making random folders under the temp directory and nodejs is triggering the windows firewall." Measured
on lothdesktop:

- The firewall log (events 2097) held rules from prompts for three `V:\ffw\tmp\ffa-*\` node.exe copies (10-12 to
  10-20). Each was a worker that downloaded node 24 into its temp folder to run ff-factory's tests (the machine's node
  is 22.17).
- A listen spy over that suite found `server/testPorts.ts` binding 0.0.0.0 41 times. Nothing else in the suite listened
  beyond loopback.
- The same day, on BEAST, an "allow finalfactory.exe" prompt for slot2-0 sat over all 12 of w1722's review clips, and
  they were published that way. On lothdesktop a slot player listened on 0.0.0.0:55000 with no prompt, because its rule
  exists. BEAST's rule for that slot was missing or wrong, and no launch said so.

**How to apply.**

- Check the listens of what you start. ff-factory's `server/listenLoopback.test.ts` fails a wide listen in its code.
- In the game repo, `scripts/nightly/player_slots.py`'s `udp_port_free` probes a port without a wide bind.
- On Windows, `Get-NetTCPConnection -State Listen -OwningProcess <pid>` and `Get-NetUDPEndpoint` show what a process
  holds. A local address other than 127.0.0.1 or ::1 needs a fixed path with a rule.
- For a clip: open its first still, a middle frame and its last frame (or the contact sheet) and look for anything that
  is not the game. Do this before `publish_review`.
