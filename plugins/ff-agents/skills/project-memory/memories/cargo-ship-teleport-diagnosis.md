---
name: cargo-ship-teleport-diagnosis
description: Root cause of cargo-ship teleporting (InserterRenderSystem camera gate) + the live-probe methodology that found it
metadata: 
  node_type: memory
  type: project
  originSessionId: 49526b53-f1a1-4f12-926b-45c0615920db
---

Cargo-ship "teleporting" (2026-07-08, branch MasterUnity60003) was NOT the LocalToFFWorldSystem
child-freeze: it was `InserterRenderSystem` refusing to sync `LocalTransform` from the fp
simulation position (`Inserter.Position`) while `placeable.GridTile` was outside camera bounds.
Sim kept flying; the stale transform ghosted on screen, then snapped 10-136u when the true
position re-entered bounds. Mode-independent (A/B measured 30 vs 32 jumps with the LtW
optimization ON vs OFF; "off = smooth" was a false negative from an idle logistics network).
Fixed by removing the gate — sync every fixed frame (presentation-only, ~dozens of moving
logistics units, no determinism impact). Verified: same save (WittlebaseDying, 10 ships in
transit), 3600-frame sweep → 0 jumps. Cargo ships = `FFComponents.LogisticsUnits.CargoShip`,
they are Inserter-family Placeables, NOT ShipMarker ships.

**Why:** any system that advances simulation ungated but syncs presentation camera-gated will
produce exactly this artifact; check for this pattern before blaming the LtW child-freeze.

**How to apply (live-probe methodology, all via MCP `execute_code`/Roslyn, no recompiles):**
- Per-frame probe = closure on `UnityEngine.Application.onBeforeRender` (sees what renders);
  self-terminating frame budget + try/catch abort; results via `Debug.Log` + `read_console`.
- Move the player autonomously by writing `LinearMotion.GravityForces` each tick from a hook on
  `PreTransformControllerUpdateNotifierSystem.OnUpdate` (LinearMotionSystem integrates + zeroes
  it; immune to MoveAction/physics fighting back — direct LocalTransform/velocity writes get
  stomped). Keyboard injection fails when the editor is unfocused.
- A/B method: reload the same save per condition for identical initial conditions; ALWAYS
  condition results on actual sim activity (idle logistics network = false negative).
- Gotchas: editor auto-pauses on console Error Pause (a failing mod threw) — disable via
  reflection `ConsoleWindow.SetConsoleErrorPause(false)` + `EditorApplication.isPaused=false`;
  unfocused editor runs ~20-30fps; `HideCargoDrones` parks drones at y=9999 (sentinel that
  pollutes drift measurements); the LtW optimization is OFF by default (StartController
  disables at boot; only the QuantumCommand enables it).

Related: [[blackhole-visual-test-recipe]]
