---
name: three-peer-lane-recipe-and-traps
description: "How to run a THREE-peer live lane (M3 built host, M5 built client A, the M5 clone editor as trigger peer B) and the five traps that each cost a run: AuditSourceRevision must be the full 40-hex sha (a short sha leaves every peer in the menu with audit-config-invalid); the ordered start host→host-ready→A→client-ready→THEN flip the clone's AutoStartInEditor (its poller auto-starts play and calls ResetForEditorLaunch; a manual EnterPlaymode stalls; an early join trips the host's pre-connect grace); flowcontrol.stall chains return only after the delay so background the stall to land a resync inside it; the clone's agent actor is player-safe and cannot audit.write (no host-vs-B comparator); cpcompare.py hardcodes --players 2 and the verdict script needs host/A to share a legId."
---

# Three-peer lane recipe and traps (2026-09-12, 069 lanes r13/r14)

- **Topology that worked:** M3 built host (`TargetClientCount: 3` — `MaxPlayers = Mathf.Max(TargetClientCount, 2)`,
  `LocalMultiplayerAutomationBootstrap.cs:672`), M5 built client A (Ben's player), the M5 clone editor
  (`FinalFactory_clone_0`, compiles HEAD from the worktree symlink, its own reclaim identity file) as trigger peer B
  joined by pid (`agent_http.py <clone pid> …`). Same-version gate: the worktree's `FFVersion.cs` must equal the
  built pair's version or the clone is rejected at the join gate (`Version|0.50.0.15`).
- **(e) `AuditSourceRevision` = the FULL 40-hex sha.** A short sha makes every peer log `audit-config-invalid …
  must be an exact 40-character hexadecimal Git revision` (`NetworkDeterminismAuditCapturePolicy.cs:275`) and sit
  in the menu; the host never reaches `host-ready`.
- **(f) Ordered start.** Launch host → wait `host-ready` → launch A → wait `client-ready` → THEN rewrite the
  clone's config with `AutoStartInEditor: true`. The editor launcher's poller auto-starts play itself
  (`LocalMultiplayerAutomationLauncher.cs:190,277`, calls `ResetForEditorLaunch` first) and ABANDONS by flipping
  the flag back to false (`:229`) when the bootstrap does not consume the config; a manual `EnterPlaymode()` skips
  the reset and stalls at `EnteredPlayMode`. A clone that joins a still-loading host trips the host's pre-connect
  grace (`LocalMultiplayerAutomationBootstrap.cs:814-850`: any peer connecting and leaving before all
  `TargetClientCount` are in ends the automation session after 10 s). Fresh leg ids per attempt — a finalized
  artifact with the same run/leg id blocks the relaunch's auto-write. Never `unity command recompile` while the
  clone is in play mode (world-null wedge: `isPlaying` true, `Ecs` NREs every frame) — exit play first.
- **(g) `flowcontrol.stall|N` returns only after N seconds** (`LocalMultiplayerAutomationCommandRunner.cs:577`),
  so a chain `stall → resync` lands the resync AFTER the window. Background the stall on A, then fire the host's
  `desync.forceresync|<B clientId>` ~1.5 s in (`lane-reset2.sh <label> <B clientId> 4 1.5`); on a LAN link a
  reset with NO stall leaves A with no backlog (clean by construction — proves nothing).
- **(h) Evidence limits.** The clone's agent actor is `player-safe` (`ActorContext.cs:44`) → `audit.write` denied →
  no host-vs-B comparator (B's own runtime detector is the only signal there). `cpcompare.py` (r12 helper)
  hardcodes `--players 2` — with three peers run `scripts/continuous_determinism_verdict.py` directly with
  `--players 3`. The verdict script requires host and A to share a `legId`; if they were launched with distinct
  leg ids, patch A's COPY (identity-only edit, state it in the report).
- **Also seen, not traced:** client A dropped (`TransportShutdown`) and auto-rejoined as a new client id the
  moment B (same SteamId, different reclaim guid) was served; the host automation errored on that disconnect
  (`Audit dwell-release gate failed … client disconnected`) and finalized its audit report while the game kept
  hosting — a host whose audit ended at session start has no checkpoint comparator for the run.
- Related: [[session-reset-marker-and-the-three-peer-backlog-fork]], [[fleet-harness-operational-2026-09-12]],
  [[dropreconnect-verb-and-injected-disconnect-verdict-record]], [[verdict-script-rejects-eviction-records]].
