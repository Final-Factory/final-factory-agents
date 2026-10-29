---
name: pair-host-for-a-placed-client-without-ssh
description: "Hosting a two-machine determinism pair for a client another worker places later (w1761, 2026-10-23, host lothdesktop, client BEAST, no ssh): match 'status host-peers-connected:' not 'host-peers-connected' (the waiting line contains it), relaunch the host every 900 s, a unique -ffAutomationLabel per attempt or the audit report is refused, devunlock fills the inventory so trash before a grab, a PostReadyCommand splits on every ';', a flow-control-too-slow drop is retried, not judged, and the host states its exact IP:port in every report marked for the client (w1940: a silent move to 7891 cost 80 minutes)."
---

# A pair host for a client placed later, without ssh (w1761, 2026-10-23)

The two-machine check of PR #2294 (circuit arithmetic): the host player ran on lothdesktop from the
worker's own sandbox (`player_slots.py launch --peer 1`, a port no other worker used), and the orchestrator
placed a client worker on BEAST with the client arguments as an attachment. It passed on the second client
attempt: the host's `ffauto:desync.stats` read 1425 compared, 1425 matched, 0 diverged over about 12 minutes.
Six traps cost three host runs first:

1. **`grep host-peers-connected` matches the waiting line.** The host writes
   `status waiting-host-peers-connected: connectedClients=1,target=2` while it waits, so a script that waits
   for a join with that word fires at once and drives a host with no client (`desync.stats` then reads
   `"clients":[]`). Match `status host-peers-connected:`
   (`LocalMultiplayerAutomationBootstrap.cs:733`, the line `WriteStatus` writes).
2. **The host gives up after 900 s without a client** (`HostPeerConnectTimeoutSeconds`,
   `LocalMultiplayerAutomationBootstrap.cs:142`; `session-ended: host-peers-never-connected`). A client
   worker placed later arrives after that: run the host in a relaunch loop on the same port until
   `status host-peers-connected:` shows, and stop on an attempt that never reached `status host-ready:`.
3. **A fixed label makes the second report collide.** With no audit capture policy the report is
   `network-determinism-audit-legacy-<label>-<role>.log` in the game's data folder, and the game refuses to
   overwrite it (`report-error: ... Audit artifact identity collision`, no report written). An earlier
   host-only run with the same label is enough. Give each attempt its own label
   (`-ffAutomationLabel "w1761-pair-$(date +%H%M%S)-$n"`); `scripts/agent/peer.py <substring>` still finds it.
   That folder is under AppData: read it, never delete or move a file there.
4. **`ffauto:player.devunlock` fills every inventory slot**, so a later `ffauto:transfer.grab` is refused
   (`InventoryTransferClientRequest Reject at transfer-bake/TargetFull`) and a value that should change does
   not. Free a slot with the replicated `ffauto:transfer.trash|<item>|<count>` first; `inventory.remove` is
   local-only (`CommandTiers.cs`, "no op, no replication") and desyncs a pair.
5. **`-ffAutomationPostReadyCommand` splits on every `;`** (`AutomationChainExecutor.Split`), so a command
   whose own arguments use `;` (`circuit.calc.set`'s line list) cannot go in it. Drive that command through
   the peer's agent channel (`peer.py ... cmd client|host`), and give the client chain only `;`-free commands.
6. **A client dropped as too slow is retried, not judged.** The first BEAST client fell behind from about 29 s
   after the join and the host dropped it at heartbeat 593
   (`flow-control-too-slow, rule=not-converging, behindSeconds=5.0, gainedSeconds=-4.9`) while the host ran
   steady (160 heartbeats per 10 s, frame p99 18 ms). The same client arguments joined clean 40 minutes later.
   Check `desync.stats` shows the client in step before driving the scenario, or the commands run on the host
   alone.

7. **The host states its exact address and port in every report marked for the client** (w1940, 2026-10-24,
   client biscuit, host lothdesktop for w1898's PR #2323). The host moved from port 7890 to 7891 between runs
   and said so only in a still-open line; the client kept joining 100.74.97.12:7890 for 80 minutes (21
   attempts, each `status error: join-timeout ... after 150s`, the log showing `Failed to connect to server`
   and `[MaxConnectionAttempts] Connection closed`), while the host waited for it. With 7891 the client was
   `client-ready` in 12 s and ran to heartbeat 587. Host: put `<IP>:<port>`, the head and the start time in
   the `For <client request>:` line, again on every relaunch that changes any of them. Client: the netcode is
   UDP, so a ping that answers with two join-timeouts in a row means the wrong port or a firewall, not a slow
   host: stop retrying, read the host's latest ledger report (`read_work <host request>`) for a new port, and
   if there is none ask with `blocked_on` reports naming the address and port you tried.

8. **A Mac host runs headless when the Mac's displays may sleep** (w2567, 2026-10-29, host m5, client BEAST, for
   w2565's PR #2822). The host's player, launched with a window, sat at load at 0.2% CPU, stuck in
   `GfxDeviceMetal::WaitForLastPresentationAndGetTimestamp`; `ioreg` showed "Display Asleep: Yes". A headless host
   (no `"windowed"` in the ffnightly scenario) loaded at once. The camera-on-content part of the brief then rests
   on the client's player, which has a window.
9. **Read the host's `desync.stats` every ~200 heartbeats, not only at the end** (w2567). When the client
   disconnects, the host's stats read `clients: []` and its counts are gone. Two w2567 runs were cut when FF
   Factory stopped the BEAST client for other workers' exclusive bench tickets (`Documentation/Bench-Lock.md`):
   161/161 and 38/38 matched, kept only because a scenario reads `desync.stats` as `w0..w9`, one every 200
   heartbeats. Give the host's join poll room (w2567 used 120 min), and have the client launch only when its
   machine has no exclusive ticket held or waiting. Then run 5 went through: 289/289 matched over heartbeats 8 to 2,312.

The scripts: a host loop that launches through `player_slots.py`, waits for `status host-peers-connected:`
and relaunches on a timeout; a driver that waits for the same line, reads `desync.stats`, then sends the
scenario's host commands through `peer.py` and logs every answer. The host's live `desync.stats` compares
every fingerprint the client sends; the client's report for `compare_determinism_reports.sh` needs the client
worker to publish it as an attachment.
