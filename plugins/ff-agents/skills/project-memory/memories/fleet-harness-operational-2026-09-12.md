---
name: fleet-harness-operational-2026-09-12
description: "Built-player fleet facts from the r8–r10 desync reproduction: a BEAST go-script nohup'd over ssh dies with the session (run it in the ssh foreground, backgrounded on the M5 side); saved-player identity is per machine (M5 = Ben's player, BEAST and M3 = Loth's); player.setposition is refused once peers are connected — use movement.goto in WORLD units; combat.respawn revives a dead local player at (0,0); fresh spawn.ships Bats never engage a camp, a pre-existing aggressive fleet does; Frenzy via ability.cast did not make them."
---

# Fleet harness facts from the desync reproduction (2026-09-12, 069)

- **BEAST launches.** `(nohup bash ./ff-beast-go-host.sh &)` inside an `ssh beast bash -lc` dies the
  moment the ssh session ends (Windows sshd kills the tree) — the go-script's `.out` stays empty and no
  process appears. Run the go-script in the ssh FOREGROUND and background the ssh on the M5 side
  (`run_in_background`); the inner `(nohup ./launch.sh &)` then survives because the go-script exits
  normally. Kill only through the owned-exe PowerShell script (`ff-beast-kill-owned-<sha>.ps1`).
- **Who controls which saved player** is decided per MACHINE (026 `ClientReclaimIdentity`), not per
  role: on the 2026-09-11 Steam save the M5 always bound Ben's player (guid tail bbbf52; dead in the
  save, `combat.respawn` revives it at tile (0,0) with hp 100 and an empty fleet) and BEAST and M3 both
  bound Loth's (433596, at his base with 8 Bats). Choose the HOST machine by the player you need to
  drive; a Mac/Mac mirror of a Windows/Mac pair is M3-host + M5-client.
- **Movement.** `player.setposition` is refused once 2 peers are connected ("would not replicate and
  would desync"); use `movement.goto|<x>|<z>|<tol>|<timeoutS>` in WORLD units (tile × 10); a chain's
  `endedHeartbeat` smaller than `startedHeartbeat` means an epoch changed mid-chain (a recovery).
- **Provoking combat.** Ten freshly spawned Bats parked beside a 3-spawner camp never engaged and the
  player took no damage in 15 min, with `ability.cast|frenzy|x|z` and `plasma` casts reported as cast;
  Loth's pre-existing 8-Bat fleet engaged immediately and its player took beam damage on the flight
  in. Drive the player whose fleet is already aggressive, or patrol THROUGH the camp
  (`movement.goto|<camp center>` then out and back) — the patrol reliably drew fire (host hp 100 → 21).
- **Fingerprint-diff workflow without the verdict script:** load both reports' `# audit-record-v1
  {"action":"Fingerprint"…}` records, key by (epoch, heartbeat), diff `fields` — the first differing
  surface is the fork (`r9/combatdiff.py`). Companion: [[diagnostic-profile-config-recipe]].
