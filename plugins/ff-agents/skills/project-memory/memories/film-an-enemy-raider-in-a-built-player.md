---
name: film-an-enemy-raider-in-a-built-player
description: "Framing one enemy raider (a new Urso unit) in a built player over the agent channel: find it from the [EnemyRaid] telemetry line's campTile, follow it by its tile because observe.state enemies caps the radius at 64 tiles, close the console with console.close (console.run|close is not a command), and expect black frames until it leaves the fog of war near the base."
---

# Filming an enemy raider in a built player (2026-10-23, w1466 Urso Ballista, BEAST)

The task: stills of a new raid-only enemy (the Urso Ballista) in a built player on a late save (°Life° copy,
`-ffFeelLoad`, `-ffAgentControl true -ffAgentControlDev true -ffEnemyTelemetry`), after `console.run|forceAttack 12`.
Four things cost a leg each:

- **`observe.state|enemies|x|z|r` caps `r` at 64 tiles**, whatever you pass (the answer says `"radius":64`). A poll
  around the player found 0 enemies for 4 minutes while the raids flew elsewhere. Find the raid in the player log:
  `[EnemyRaid] t=... campTile=(-675,-485) target=(-7,-6) ... units=Urso_Ballista:1,...` (`-ffEnemyTelemetry`).
  `campTile` is in tiles; `target` is a chunk, 64 tiles a side. Poll `enemies` at the camp tile within a second of the
  line, then re-centre on the unit's own `tile` every second.
- **World = tile x 10** for `camera.focus|<wx>|<wz>|<dist>` (player at tile (68,-230) sat at world (682.8,-2296.2)).
- **`console.run|close` is not a console command**: it prints an ArgumentException and leaves the Quantum console open
  over the picture, and with it open the `camera.focus` frames stayed on the player's base. Use `ffauto:console.close`
  after every `console.run`.
- **Unexplored space renders black (fog of war)**. A raider filmed from its camp is invisible for most of its flight:
  on °Life° the Ballista was black for 57 s and visible 59-63 s, from leaving the fog at the base edge until the
  player's fleet killed it. Record the whole flight (`scripts/live/live_frames_dump.py --fps 30 --seconds 90` while
  following) and cut the stills from the last seconds before `observe.state` loses it.

A late save's defences kill a raid in seconds (`ursoKilled` in `[EnemyCensus]` rose 576 in 67 s), so the forced raid
from the nearest camp to explored space gives the most frames. The working loop (force raids until one carries the
unit, locate, follow, dump) is the four bullets above in that order; its stills are FinalFactory#1929's
`ballista-builtgame-*.jpg`.

Also on BEAST: an urgent release's bench-lock hold ran past its 30-minute turn (09:17Z to after 09:55Z), so
`player_slots.py launch --bench-wait 1800` gave up; behind an urgent release wait 3600 (`Documentation/Bench-Lock.md`).
