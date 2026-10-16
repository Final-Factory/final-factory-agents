---
name: relay-drop-in-a-built-player
description: Causing a real Unity Relay drop on a host in a built player (w1386, m5, 2026-10-16) - freeze it with SIGSTOP for ~85 s and resume; NGO ends the host inside the transport event and destroys its player there, so anything that must read the host's world on a relay loss runs in OnTransportFailure, not in the disconnect delegate
---

# A real relay drop in a built player, and what the host still has when it hears of it

w1386 made a host save before a relay loss sends it to the title screen, and proved it with a real drop.

**The drop.** Launch a development player as a relay host with `scripts/nightly/player_slots.py launch --detach <app> --
-ffAutomationRole host -ffAutomationRelay true -ffAutomationTargetClients 1 -ffAutomationFlatMap true -ffQuitAutosave
-ffAgentControl true -ffAgentControlDev true -ffDeckTour <tour> ...` (the JSON it prints has the pid). Let it play
20 s (a tour `wait`), then `kill -STOP <pid>`, wait 85 s, `kill -CONT <pid>`: on resume the relay answers "player timed
out due to inactivity" and NGO raises "Transport failure!" for real (w673 measured 15 s and 40 s of silence survived,
75 s not). `ffauto:net.hosttransportfail` is NOT the same: it calls `Shutdown(true)` only and never raises
`OnTransportFailure`, so code hooked there does not run. A host on local UTP is not on a relay at all. The run script:
`/srv/fff/review/w1386-relay-loss-autosave/relay-drop.sh.txt` (leg B loads the save with `-ffAutomationRole solo
-ffAutomationSave <name>`). Name the automation role: an `_automation` process saves into its own files and index, never
into the person's autosave rotation on that Mac.

**What is left when you hear of it.** NGO raises `OnTransportFailure`, then shuts the host down inside the same
transport event (`NetworkConnectionManager.TransportFailureEventHandler`), and that teardown destroys the host's player
(its PlayerDataController and entity) before any later frame. The disconnect delegate
(`HandleServerStopped` -> `LeaveGame` -> `DisconnectedFromGame`) comes after: a save requested there captured 1 entity
and did not load ("Corrupt Save? No player entities found in save file"). Capture in `OnTransportFailure`:
`HostConnectionLossNotice.RecordTransportFailure` starts the autosave and `SaveCaptureSystem.TakePendingNow` takes its
immediate capture on the spot (`SaveGameManager.CaptureInto`); the leaving steps only wait for it. A held capture would
never come: no heartbeat follows a lost relay.

Related: [[live-mp-repro-harness-notes-2026-09-23]], [[built-mac-player-ui-capture-resolution-and-clips]]
