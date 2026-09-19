---
name: comet-detector-and-the-swamped-census-change-detector
description: "How to know an ambient comet is in flight on a built-player leg (074 T110 proof): the symmetric CensusDetail diagnostic profile + cometwatch.sh, a byte-offset tail of host-terminal-LEG.log for a CensusDetail row whose type list contains FFComponents.Map.Comet (not CometCore/Fragment/Catcher). The naive detector — 'census hash changed on an idle world' — is SWAMPED (this world changes census on ~50 % of heartbeats); no ffauto verb or snapshot scope can see a comet. Spawn odds and lifetime."
---

# The comet detector, and why the naive one is swamped (074 T110, 2026-09-19)

**Why it was needed.** T110 (comets never marshalled) could only be PROVEN by a join/recovery
served while a comet was in flight. Nothing in the agent-control surface can see one: no `ffauto`
verb reports comets, `snapshot`/`nearby` list grid structures + pickupables only. The runtime
census fingerprint sees it — but only as a hash.

**Detector that worked** — the symmetric `CensusDetail` diagnostic profile
([[audit-capture-policy-must-be-symmetric]]) plus `E/cometwatch.sh LEG [maxSeconds]`:
tail `host-terminal-LEG.log` from its CURRENT byte offset (no rescans of a 200 MB file), grep
each new chunk for a `CensusDetail` row matching
`^\[DeterminismAudit\]\[Heartbeat N\]\[Epoch E\]\[role\].*FFComponents\.Map\.Comet[],]` — the
trailing `[],]` excludes `CometCore`, `CometFragment`, `CometCatcher` — print the heartbeat/epoch
and the `sig=… n=… types=[…]` fragment, exit 0; exit 2 on timeout. Proven positive on an old
report before trusting it (9 hits on `client-g5d-cp1-report.log`). On t8 it fired at ep2 hb 7731
(`[LinearMotion, Comet] n=1`); the `desync.inject` at hb 7943 was served at hb 7945 with the
comet 214 hb old, and the recovered peer stayed equal through the comet's death.

**Detector that does NOT work.** "The census hash changed while nobody acted, so something
spawned" — this world changes `census` on about half of all heartbeats (t7 host ep2: 788 changes in
1577 hb; miners, projectiles, pickups, arrows). A naive change detector fires constantly.

**Odds.** `CometSpawnerSystem.cs:59` rolls `CoinFlip(0.005 * dt)` per heartbeat (~one comet every
3,200 hb ≈ 3.3 min at 16 UPS; `:62` 10 % chance of two); a comet lives 60 s = 960 hb. A
comet-free window is therefore never guaranteed — detect, do not assume.
