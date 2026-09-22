# Co-op board — honest game 074-h, sitting <LEG> (three agents, one per machine)

Every agent: read this file before each new goal and at least every ~10 minutes; append to it
(never rewrite other agents' lines). One line per entry, prefixed with your role and the host
heartbeat, e.g. `[m3 hb 51200] claimed iron asteroid (31,-27) for a mining station`.
ONE shared world: research, the objective tracker and the tech tree are shared; inventories are
per player; buildings any player places belong to the team.

## Roles
- **host (M5)** — BASE BUILDER + RESEARCH OWNER: main production lines, power, the research queue
  (only the host changes research), and the saves.
- **m3 (M3 client)** — RESOURCES & LOGISTICS: new mining stations, ore throughput, logistics that
  bring materials to the base; supplies the host's requests.
- **beast (BEAST client)** — FLEET, DEFENCE & EXPLORATION: crafted fleet, base defence, clearing
  threatening camps, scouting end-game sites (HowToPlay §4), later megastructure sites.

## Rules for everyone
- Honest play only; the guard enforces it; never work around a refusal.
- Drive ONLY your own player: `$E/peer.sh <your-role> METHOD ROUTE [JSON]`.
- Claim an area here before building there; never build inside another role's claim.
- Only the host saves (`claude_playtest_074-<LEG>-<slug>`).
- Desync check after each batch: `grep -c divergedSurfaces $E/host-terminal-<LEG>.log` and
  `grep -c "status error" $E/host-terminal-<LEG>.log`; nonzero → STOP, post it here, report.

## Current team goal
<carry over from the previous sitting's board / handoff>

## Claims
<carry over still-valid claims from the previous board>

## Requests

## Log
