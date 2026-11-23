---
name: stage-a-station-drone-scene-over-ffauto
description: "Setting up a mining or research station with drones in an editor or built player over ffauto (w5336): spawn.ships then fleettransfer.give puts drones in a station, construction.deleteimmediate is silently refused for a built Mining Station so use construction.remove with the player near it, player.setposition takes tiles and its jump explores the fog on the way, and record_clip needs FF_GAME_DATA_DIR to find a slot player's session."
---

# Stage a station-drone scene over ffauto (2026-11-23, w5336 drone vision, LothDesktop)

The task: a built-player clip of orphaned drones flying from a removed home station to a far one through the fog. Each
of these cost a leg:

- **Drones into a station:** `spawn.ships|Miner Bot|4`, then `fleettransfer.give|Miner Bot|4|<x>|<z>` at the station.
  A `give` from inventory alone did nothing until the ships were spawned.
- **`construction.deleteimmediate` refuses a built Mining Station without a word** (the host's UnbuildValidator admits
  only some classes; built-pair-lab-traps saw the same for solars). Use `construction.remove|<x>|<z>`, and move the
  player near first: the construction bots stay with the player, so a far removal never starts.
- **`player.setposition|<x>|<z>` takes tiles** (world = tile x 10), and the jump explores the fog along the way (seen
  twice). Before saving a scene that must show unexplored ground, clear the explored map: in an editor `execute_code`,
  `ExploredStore.Clear()` plus the `Clear()` of FogManager's private stampers (`_stationGround`, `_droneSight`,
  `_stamps`) by reflection, then `game.save|<name>`; load it in the player with `-ffSoloLoad <name>`.
- **The dev cheat is `player.devunlock|8`**; plain `devunlock` is an unknown command.
- **record_clip `--player`/`--do` found no agent session** for a slot player that writes under `FF_GAME_DATA_DIR`
  (w5297): it read `AgentControl/session-<pid>.json` under the old data root only. Fixed in ff-agents 1.37.7 (it reads
  `FF_GAME_DATA_DIR` too). On an older copy: record with `--pid <pid>` and send each command with the game repo's
  `python scripts/agent/peer.py <label> cmd client "<ffauto>"`. A solo player started without `-ffAutomationRole host`
  is `client`, and `host` raises KeyError.
- **An editor eval that reads `realtimeSinceStartup` is refused** without a bench ticket; count `Time.frameCount` to
  pace a non-timing probe instead.
