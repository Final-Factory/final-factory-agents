---
description: "074 t72c–t74 (2026-09-22): the Dark Star Gate is powered by its OWN built Spawner Chests (frame after attacks → satisfaction 0; rebuild via cbots + parts; toggle.cbots|on = STOPPED); runtime verdict divergedSurfaces are indices into DeterminismStateFingerprint.WireSurfaceNames, not the verdict script's order; the 16,384 fingerprint cap keeps the FIRST records so checkpoint before the interesting window; mobilestation.place rejections are silent and Command Core is not IsShip; observe.state|nearby has no construction stage; BEAST launch must be (ssh -n … &) with stdin redirected, macOS has no timeout; a recovery epoch never latches a diagnostic anchor."
---

# Built-pair lab traps, 2026-09-22 (074 t72c / t73 / t74)

- **Gate power is its own Spawner Chests.** The "Powered Dark Star Gate" blueprint rings the gate
  with 10 Spawner Chests + 5 connectors; a built chest produces 500 power (dyson.factory doc). After
  an attack-heavy run they are `frame` and the gate reads satisfaction 0 / draw 2000 — Dyson output
  does not help. Rebuild: `spawn.ships|Construction Bot|6`, `inventory.add|Spawner Chest|10`,
  `inventory.add|Connector|5`, player within range. `toggle.cbots|on` means STOPPED.
- **Verdict `divergedSurfaces` = indices into `DeterminismStateFingerprint.WireSurfaceNames`**
  (0 grids,1 power,2 playerSimPos,3 cbots,4 pickupables,5 minerBots,6 asteroids,7 fleets,8 dysonDrones,
  9 massDriven,10 haulers,11 containers,12 directions,13 toggles,14 camps,15 attacks,16 loot,17 combat,
  18 beltItems,19 movers,20 vision,21 census). Decoding with the verdict script's FINGERPRINT_ORDER is wrong.
- **The 16,384-record fingerprint cap keeps the FIRST records.** t74's forks at epoch3/hb24712 and
  epoch5/hb192 exist only as lifecycle/verdict records; a recovery reset also discards the client's
  pre-recovery rows. Checkpoint every peer just before the window you care about.
- **A recovery epoch never latches a diagnostic anchor** (only a real join starts a block): t74's
  epoch-2 anchor never latched after the join-time recovery; CampsDetail/AttacksDetail captured 0.
- **`mobilestation.place` rejections are silent** (`MobileStationPlacementClientRequest.cs:136`):
  the item simply stays in inventory. `Command Core` is IsShip=0 (not placeable); `Hauler` is IsShip=1
  but was still rejected from the M3 client three times (collision vs inventory unknown). Place from
  the host first, whose Reject audit record is readable before the critical buffer overflows.
- **`observe.state|nearby|x|z|r`** lists structures with `state` (built/frame), power satisfaction/draw
  and settings, plus asteroid/pickupable COUNTS — never `ConstructionTracker.CurrentStage`.
- **BEAST client launch:** `(ssh -n beast '"C:\Program Files\Git\bin\bash.exe" -lc "bash …/beast-client-<leg>.sh"' > out 2>&1 &)`
  with the script's `nohup … < /dev/null &`; a plain ssh holds the channel until the player dies and
  then RESUMES the rest of your chain (t72 launched an orphan M3 client that way). macOS has no `timeout`.
- **Fleet-transferred Dyson Bots do not become Dyson drones** — the platform only counts drones that
  arrive through the assembler/spawn path; and they were irrelevant to gate power anyway.
