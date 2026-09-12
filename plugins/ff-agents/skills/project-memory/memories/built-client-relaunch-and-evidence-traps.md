---
name: built-client-relaunch-and-evidence-traps
description: "Built-player fleet traps from the 2026-09-12 r11 lane: a client in the menu refuses EVERY ffauto command (409 state_not_playable) so a dropped client must be RELAUNCHED, never net.rejoin'd; a relaunched client with the SAME AuditRunId/LegId cannot auto-write its report if the earlier artifact exists (IOException on artifact identity) — move the old artifact first or the verdict-epoch evidence is lost; lane signal counters must fail closed (unreachable peer = NA, never an empty field; grep -c exits 1 on a zero count); LAN-address joins failed (MaxConnectionAttempts) while Tailscale addresses join fine."
---

# Built-client relaunch and evidence traps (2026-09-12, 069 lane r11)

- **A client in the menu is dead to the harness.** After a transport loss + failed reconnect the built client
  sits in `state: menu`, and every `ffauto:` chain — including `net.rejoin` and `audit.write` — returns
  `409 state_not_playable "commands need a running game; the game is 'menu'"`. Kill the process and relaunch
  from its launch script (rename its terminal log first: the script refuses to start over an existing log).
- **Move the old audit artifact BEFORE relaunching with the same run/leg id.** The auto-write on give-up
  (`ReconnectGaveUp` → lifecycle `error` → `report-writing`) fails with `report-error … System.IO.IOException:
  Audit artifact ident…` when `…/DeterminismAudit/network-determinism-audit-<runId>-<legId>-client.log` already
  exists from the previous launch — and a menu-state client cannot write it manually. The r10b epoch-14
  desync verdict (ten surfaces at hb 8 after a reconnect-join) lost its client-side fingerprints this way.
  Either rename the previous artifact away or give the relaunch a new `AuditLegId`.
- **Signal counters fail closed.** A lane that greps each peer's log over ssh must print `signals=NA` when the
  ssh fails and must only treat `signals=[1-9]` (or `state=menu`) as a signal; an empty field once read as a
  fork and triggered a pointless checkpoint. `grep -c` exits 1 on a zero count — `$(grep -c … || echo NA)`
  prints BOTH `0` and `NA`; use `$(grep -c …; true)`.
- **Address choice.** With the M5's Tailscale link flapping (ssh to both machines resetting/timing out for
  minutes at a time, both clients dropping with `TransportShutdown`/`ProtocolTimeout`, hosts evicting them
  `flow-control-hard-drift`), joining the hosts by LAN IP instead failed with `MaxConnectionAttempts` even
  though both hosts bind `*:port` and direct-LAN ssh (`ssh -F /dev/null user@10.0.0.x`) worked — unexplained;
  the Tailscale addresses join fine whenever the link is up. Each auto-reconnect is a NEW join (new client id,
  new epoch), so a climbing epoch counter with 0 recoveries means link flaps, not desyncs.
- Companion: [[verdict-script-rejects-eviction-records]], [[fleet-harness-operational-2026-09-12]].
