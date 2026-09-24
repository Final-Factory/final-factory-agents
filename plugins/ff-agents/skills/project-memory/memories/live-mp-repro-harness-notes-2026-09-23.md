---
name: live-mp-repro-harness-notes-2026-09-23
description: "Operational facts from the overnight three-peer live-MP repro lane (074, 2026-09-23): run built players headless overnight; per-epoch detail needs the LEGACY capture path (it is huge), because the diagnostic profile anchors one block; runtime verdicts are audit records, not log lines; the new SimulatedSend* latency fields; editor probe-load stalls and a corrupt probe save that looked like a bug."
---

# Live-MP repro harness notes (074, 2026-09-23)

- **Headless overnight.** Windowed built players (`-screen-fullscreen 0 …`) sat at
  `waiting-title-menu` at 0.4 % CPU overnight. Use `-batchmode -nographics` on all three peers
  (BEAST can then launch straight over ssh, with no schtasks desktop session). A launch that failed
  config validation burns its leg id, so relaunch as the next id.
- **An unlimited dwell needs v3-continuous.** `AuditDwellReleaseTimeoutSeconds: 0` with any other
  schema is refused (`audit-config-invalid … may be unlimited only with verification-v3-continuous`).
- **Per-epoch detail.** The diagnostic profile anchors ONE heartbeat block and never captures
  post-recovery epochs (`NetworkDeterminismAudit.cs:206-217`; `AuditDiagnosticEpoch: 0` does not
  change that). For hb <= 8 detail in every epoch, drop the typed audit fields (`AuditRunId`,
  `AuditLegId`, `AuditSourceRevision`, `AuditSaveName`, `AuditSaveSha256`, profile/schema) so the
  legacy path runs. It dumps CampsDetail at hb <= 1 and every 60, and AttackScheduleDetail at hb <= 8
  and on every final step. Cost: ~150 MB/min per peer, so extract with grep on each machine and
  delete. Diff with a per-(epoch,hb) keyed script.
- **Verdicts.** The runtime detector's verdicts appear as `# audit-record-v1 {"phase":"desync-verdict"…}`
  and `RuntimeDesyncDetectorSystem -> DesyncRecoveryAttempt/Succeeded/Failed`. Grep for those, not
  "Multiplayer desync detected". In a RELEASE Player.log, a verdict that immediately starts a recovery
  is dropped (the reset clears the notification queue before the drain). Count the report files, not
  the log lines.
- **Internet-like runs.** Automation configs take `SimulatedSendDelayMs`, `SimulatedSendJitterMs` and
  `SimulatedSendLossPercent` (Unity Transport simulator; editor and dev builds only). Set them on
  every peer and check for the `network-shaping-applied` status line. Live players use Unity Relay
  across the internet, while LAN/Tailscale legs have ~0 latency.
- **Forcing the live sequences.** `desync.forceresync|<clientId>` on the host forces a serve. To get a
  RecoveryFailed kick, `desync.inject` on the client the moment each `DesyncRecoverySucceeded` lands,
  twice inside the 60 s probation. A kicked client sits at the menu, where agent commands are
  refused, so relaunch the player to rejoin (reclaim by guid).
- **Editor probe loads.** `SaveGameManager.LoadGame` from `execute_code` often stalls at hb 0 (or a
  later call silently does nothing). Re-issue it until the heartbeat is seen to reset to 0 and
  `StationGrid` count > 0 before dumping. Never trust a probe save written around a stalled load:
  `probe_census_A` (2026-09-22) held scrambled connection ids (310/555 stations pointing at
  wrong same-type stations, 1 grid vs 58) and produced a false "58 vs 1 grids across reload" lead.
  Check the probe save itself by reloading it and counting connected components.
- **Unity Relay legs (`44cffffbe`, 2026-09-23).** Live players connect through Unity Relay, and harness legs
  can too, with no Steam involved (Relay sign-in is anonymous).
  - Host config: `UseRelay: true`. It logs `status relay-join-code: joinCode=XXXXXX`.
  - Put that code in each client config's `RelayJoinCode`. Rejoin with `net.rejoin|relay|<code>`.
  - Leg r1 (three machines, e2 scenario over real Relay) was clean.
- **Ben, 2026-09-23: testing never goes through Steam.** Copy local builds to the three machines; upload to the
  beta branch only when Ben asks for a beta. A Steam upload costs him a manual login.
- **Bystander watchdog trips during another peer's load (T158) — fixed `925e005f2`.**
  - Tell: a bystander logs `[Reconnect] WatchdogTripped appliedAgeSeconds=5.1` about 5 s after
    `NotifyFlowControlWaitingRpc waiting=True,peers=<other peer>`, typically 60-90 hb after that peer was served.
  - The host then sees `SessionEnded:Superseded` and a reclaim. Watch for it as a regression.
- **Relay + send shaping together (legs r2/r3, 2026-09-24) — clean.** All three peers log
  `network-shaping-applied` after the Relay join. Before `3938c0cb1` a `net.rejoin` silently dropped the
  rejoiner's shaping (Shutdown disposes the transport driver); the fix re-applies it, and each rejoin now logs a
  SECOND `network-shaping-applied` — count them per client to confirm.
- **A rejoin gives the client a NEW clientId.** A `desync.forceresync|<id>` aimed at its old id is a silent
  no-op: r1-r3's post-rejoin serves did nothing. Read the new id first (the rejoiner's `status client-ready:
  localClientId=N`, or the host's connect lines), and check a `DesyncRecoveryBegin … clientId=N` follows every
  forced serve.
- **Leg monitor pipelines: every stage must flush per line.** `grep --line-buffered | sed -u | cut -c…`
  delivered NOTHING for a whole leg because `cut` block-buffers. Drop `cut` (or use `awk '{print
  substr($0,1,200); fflush()}'`), and prove the monitor emits one known line before trusting its silence.
