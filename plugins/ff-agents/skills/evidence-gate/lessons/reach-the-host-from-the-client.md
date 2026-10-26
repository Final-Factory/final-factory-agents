---
name: reach-the-host-from-the-client
description: "A host address works only from the machines that can route to it: a LAN address answers on its own LAN, a Tailscale address from every machine on the tailnet. Before a client leg builds or joins, ping the host from the client's own machine (`python scripts/nightly/reach.py @<machine>` in the game repo), join the first address that answers, and stop at once naming every address tried when none does. Lab configs name the machine (`\"hostAddress\": \"@m3\"`, resolved through `scripts/nightly/lab_hosts.json`, Tailscale first), never a copied IP. w2252: LothDesktop lost every ping to the m3's LAN address 10.0.0.110 and sat through a 150 s join timeout; the Tailscale address worked."
date: 2026-10-26
---

# Reach the host from the client's machine before it joins

**Rule.** An address that works from one machine is a claim about that machine only. Before a client leg builds or
joins a host on another computer:

1. **Probe from the client's machine**, not from yours or the host's: `python scripts/nightly/reach.py @<host machine>`
   (game repo; the machine's addresses are in `scripts/nightly/lab_hosts.json`), or `reach.py <addr> <addr>` with the
   addresses the host leg posted. It ends `PICKED <ip>` (join that one) or `UNREACHABLE: ... tried ...`.
2. **Prefer the Tailscale address.** Every machine on the tailnet routes to a 100.x address; a 10.0.0.x or 192.168.x
   address answers only on its own LAN. Keep LAN as the fallback for a client whose Tailscale is stuck (w1982).
3. **On no answer, stop and say so**: name every address tried, tell the other legs, and let another machine take the
   leg. Never let the game's join timeout be the probe.
4. **Name machines, not IPs, in configs and skills**: `"hostAddress": "@m3"` in a lab config, `m3` (MagicDNS) in a
   script default. One file holds the addresses, so a changed one is fixed once.

**Why.** w2252 (2026-10-26, the Leech target-scan pair for PR #2590): `lab.m3.json`, `lab.pair-m3-beast.json` and
`lab.pair-m3-rosetta-beast.json` hardcoded the m3's LAN address 10.0.0.110, as did the determinism-audit skill's
`CLIENT_HOST` default. It had always worked because the only client was BEAST, on the same LAN. When the client leg
moved to LothDesktop, every ping to 10.0.0.110 was lost and the first join timed out after 150 s; the m3's Tailscale
address 100.104.235.48 answered and the join worked. w1976 (2026-10-24) was the same miss from the other side: a client
built its player for 10 min before learning its own Tailscale was stuck.

**How to apply.** The merge checklist's pair-run line asks for the probe's `PICKED` line from each client machine.
ffnightly runs the same pick before every remote join (`ScenarioRun.host_address`, w2259), and
`scripts/tests/test_nightly_reach.py` fails on a lab config that hardcodes a non-loopback address.
