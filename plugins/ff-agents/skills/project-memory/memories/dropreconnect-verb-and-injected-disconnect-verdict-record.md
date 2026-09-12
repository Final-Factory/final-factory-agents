---
name: dropreconnect-verb-and-injected-disconnect-verdict-record
description: "ffauto:net.dropreconnect|N does NOT hold the link down for N seconds — it only suppresses the client connection probe for up to 10 s or until a reconnect episode is active, and on a LAN-quality link the ReconnectEngine restores at attempt 1 in ~2 s for N=10 and N=60 alike; a multi-attempt flap needs a real link fault. The chain comes back 'cancelled after 0 of 1 segment(s)' (not a failure), and the injected disconnect writes an AuditLifecycle phase=error dwell-gate record on the HOST that makes the verdict script return evidence-invalid — filter it like an eviction record."
---

# `net.dropreconnect` reconnects at once, and its disconnect record poisons the verdict (2026-09-12, 069 lane r12a)

- **The outage argument is a probe suppression, not a link fault.** The client logs `Injected outage
  announced; suppressing the client connection probe for up to 10s or until a reconnect episode is
  active`, then `DisconnectClassified class=TransportLoss … TransportShutdown`, `ReconnectAttempt(1)
  max=4 backoffSeconds=2.0`, `ReconnectRestored attempts=1 episodeSeconds=2.1` — identical for
  `|10` and `|60`. Each restore is a NEW join (new client id, new epoch). To reproduce a multi-attempt
  flap (the r10b epoch-14 ten-surface reconnect-join verdict, Client-4…8 over minutes of Tailscale
  loss) you need a real fault: a pf/firewall rule or pulling the interface on the client for 30-60 s.
- **The chain result is `cancelled after 0 of 1 segment(s)`** with `endedHeartbeat: 0` — the engine
  cancels chains on the disconnect; the verb worked. Poll `GET hello` for `state: playing` with a
  new `epoch` instead of trusting the chain status.
- **The HOST report gets an unhealthy lifecycle record**: `AuditLifecycle phase=error` "audit
  dwell-release gate failed because the session ended: client disconnected from host" at the injected
  disconnect. `scripts/continuous_determinism_verdict.py` then returns `evidence-invalid` for EVERY
  window of that report (`reject_unhealthy_record`, whole-file scan). Same method as for evictions:
  `filter_unhealthy.py IN OUT host` drops exactly that record (list it), corrects the footer, and the
  rejoin epoch compares normally (r12a d1: 2050 samples pass; d2: 2021 samples pass). The client
  report needs no filtering for this shape.
- Related: [[verdict-script-rejects-eviction-records]], [[built-client-relaunch-and-evidence-traps]].
