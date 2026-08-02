---
name: massdriver-visual-e2e
description: Agent-runnable visual + behavioral e2e regression for mass drivers (feature 012). Boots a solo FlatMap world with a three-pair mass-driver cell (in-range, exact-boundary, out-of-range), asserts the laser in-range indicator, live firing/delivery, and the receiver-capacity gate via execute_code (objective pass/fail), and captures game-view screenshots of the laser states and a frozen mid-flight projectile. Run after any change to MassDriverSystem, MassDriverAnimationSystem, the range predicate, or mass-driver presentation.
---

# Mass-driver visual e2e regression

Verifies IN THE LIVE GAME what the unit tests and determinism gates cannot: that the laser
in-range indicator agrees with the tile-derived fire gate, that projectiles visually fly and
deliver, that an out-of-range (but powered and loaded) driver stays dark and silent, and that
the receiver-capacity gate stops launches when the destination is full.

**Scenario**: `ValidationScenarios/massdrivers/massdriver-visual.ffbp.txt` — three sender→receiver
pairs (radius 40 tiles): A in-range (20 tiles), B exact boundary (40 tiles), C out-of-range
(45 tiles, fed items + power exactly like the others — the only thing keeping it dark must be
RANGE). ⚠️ **The paste re-anchors the blueprint** (centers it on the paste position), so authored
tiles shift by a constant offset; relative geometry (the pair distances) is preserved exactly.
Never assert against absolute tiles — the snippets below identify drivers by their
target-distance instead.

First run + baseline screenshots: 2026-07-05 (feature 012) — PASS, all assertions + captures.

## Prerequisites

- Unity editor open on THIS project, Edit mode, compiled clean. Pin the MCP instance
  (`mcpforunity://instances` → `set_active_instance`) — see CLAUDE.md.
- No paired audit or other play-mode session in flight (`.ff-local-automation.json` absent).

## Procedure

### 1. Boot the world (host-only automation session, no client)

Read the `ffblueprintstart…` line from the scenario file, then write `.ff-local-automation.json`
to the repo root:

```json
{
  "Enabled": true, "AutoStartInEditor": true, "ForceOutOfGameStartMode": true,
  "Role": "Host", "Host": "127.0.0.1", "Port": 7777, "Seed": "automation-smoke",
  "FlatMap": true, "EnableDeterminismAudit": false, "Label": "massdriver-visual",
  "WriteReport": false, "AutoQuit": false, "ExitPlayModeOnComplete": false,
  "TargetClientCount": 2,
  "PostConnectDelayMs": 60000,
  "PreConnectCommand": "ffauto:blueprint.place|<STRING>|0|0;ffauto:player.setposition|10|2"
}
```

- No client ever joins, so the session stays live indefinitely for inspection. The editor's 1s
  poller auto-starts play mode; wait for `Placing blueprint` in the editor log (~30s), then give
  the sim ~10s before asserting.
- The park at tile (10,2) puts the camera on the exact-boundary pair (the paste shifts the cell
  so that pair lands around z≈1). To view another pair later, teleport from `execute_code`:
  `Behaviours.Multiplayer.LocalMultiplayerAutomationCommandRunner.TryExecute("ffauto:player.setposition|0|62", out var r)`
  (works while solo/pre-join; the camera follows the player — but NOT while paused).
- **Cleanup when done**: delete `.ff-local-automation.json`, exit play mode (`manage_editor`
  `stop`), and delete any `Assets/Screenshots/massdriver-e2e-*` captures (+ `.meta`) so they are
  not committed. A leftover config auto-starts play on the next editor boot.

### 2. Objective assertions (execute_code — the pass/fail)

⚠️ **Never `Thread.Sleep` in `execute_code`** — it runs on the main thread, so sleeping freezes
the whole engine and you sample a frozen world (heartbeats do NOT advance). Sample across
separate calls instead. Namespaces that bite: `ScalableLaserOwner` is
`FFComponents.LogisticsUnits`, `FFGrid` is `FFComponents.Map`, `FFConfig` is `FFConfiguration`.

**2a. Laser truth table** (expect `LASERS OK`):

```csharp
var em = Unity.Entities.World.DefaultGameObjectInjectionWorld.EntityManager;
var q = em.CreateEntityQuery(typeof(FFComponents.MassDrivers.MassDriver),
  typeof(FFComponents.LogisticsUnits.ScalableLaserOwner), typeof(FFComponents.Core.Placeable));
var ents = q.ToEntityArray(Unity.Collections.Allocator.Temp);
var results = new System.Collections.Generic.List<string>(); var ok = true;
foreach (var e in ents)
{
  var md = em.GetComponentData<FFComponents.MassDrivers.MassDriver>(e);
  var laser = em.GetComponentData<FFComponents.LogisticsUnits.ScalableLaserOwner>(e).IsOn;
  var myTile = em.GetComponentData<FFComponents.Core.Placeable>(e).GridTile;
  if (md.Destination == Unity.Entities.Entity.Null)
  { if (laser) ok = false; results.Add("receiver laser=" + laser + " want=False"); }
  else
  {
    var destTile = em.GetComponentData<FFComponents.Core.Placeable>(md.Destination).GridTile;
    var dx = destTile.x - myTile.x; var dz = destTile.z - myTile.z;
    var tiles = (int)System.Math.Round(System.Math.Sqrt(dx * dx + dz * dz));
    var want = tiles <= 40;
    if (laser != want) ok = false;
    results.Add("sender d=" + tiles + " laser=" + laser + " want=" + want);
  }
}
ents.Dispose();
return (ok ? "LASERS OK" : "LASERS FAIL") + " [" + string.Join("; ", results) + "]";
```

Expected: `sender d=20 → True`, `sender d=40 → True`, `sender d=45 → False`, all receivers False.

**2b. Delivery + range-silence** — read each RECEIVER's (Destination==Null driver's) total
inventory: after ~1 min of uptime the d=20 and d=40 receivers hold >0 delivered items and the
d=45 receiver holds EXACTLY 0. (Do NOT use the Cargo Holds — the receiver→connector→hold drain
does not flow in this scenario; receivers accumulate instead.)

**2c. Capacity-gate stall (bonus, verifies the C5 fix live)**: receivers fill at 164
(`NumCanAdd == 0`) and their senders then hold fire at `ReadyToFire == true`. To resume launches
(for the flight capture), zero the receiver Primary slots from `execute_code`; launches resume
within one cycle (~3s, CarryCapacity 30 per launch).

### 3. Screenshots (subjective look — beam, projectile, no-beam)

1. Capture per the drive-game skill's "📸 Screenshots — THE canonical recipe" (the only copy):
   Free Aspect first, then the composited `manage_camera` game_view capture (Channel A, no
   `camera` param). Blank/white → re-run the Free Aspect menu item and re-capture.
2. **(a) Beam ON**: parked at the boundary pair — the red beam spans sender→receiver.
3. **(b) Projectile mid-flight (catch-and-pause)**: flights last only ~0.6-1.1s of each 3s
   cycle, so don't screenshot blind. In one `execute_code` call: if
   `MassDrivenItem` count > 0 → set `GameMetaState.IsPaused = true` (via
   `FFCore.Extensions.Ecs.Get/SetSingleton`) and return the projectile's progress; else return
   "retry" (repeat the call — each try is instantaneous). At `progress≈0` the projectile hides
   inside the sender: unpause, immediately re-run the catch call to freeze it mid-beam, then
   capture. Unpause afterwards. (If receivers are full, do 2c first.)
4. **(c) Beam OFF**: unpause (camera does not follow while paused), teleport to the
   out-of-range pair (see §1), capture — driver visible, NO beam.

## Pass criteria

- 2a returns `LASERS OK` (d=20 ON, d=40 ON, d=45 OFF, receivers OFF).
- 2b: in-range receivers accumulated items; out-of-range receiver has exactly 0.
- 2c: full receivers stall their senders; clearing resumes launches.
- Screenshots: beam on the in-range pair; frozen projectile on the beam; no beam out-of-range.
