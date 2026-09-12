---
name: headless-windows-player-over-ssh-and-placement-route
description: "Running the tutorial across BEAST (Windows) + M5 (Mac) built players: BEAST has no logged-in desktop so its player runs HEADLESS over SSH (agent control works, pointer/ui verbs don't, ability objectives don't tick) — so the M5 windowed player HOSTS; native pointer mapping for the 1280x800 M5 window; the inventory→ghost placement route and its three blockers; fresh-world verification configs need AuditSaveName generated:<seed>; movement.goto is WORLD units; PYTHONIOENCODING on Windows; the client's only desync signals."
---

# Headless Windows player over SSH, pointer mapping, and the placement route (2026-09-11, 069)

**BEAST cannot host a windowed player.** `qwinsta` shows a console session with no user, so an
Interactive scheduled task never runs (result 267011). Windows players run HEADLESS from SSH
(`-batchmode -nographics`, launched from Git-bash with `nohup … &` into Session 0). Agent control
works headless (`GET hello` answers) but `pointer.*`/`ui.*` have no frame, and the tutorial's
Frenzy/Afterburner/Plasma objectives only tick from real input actions (`MultiUnitCastAbility.cs:62`,
`PlasmaBoltAbilityAction.cs:202`, `AfterburnerAction.cs:116` → `AbilityNotifierService.OnAbilityUsed`;
`ffauto:ability.cast` bypasses them, `LocalMultiplayerAutomationCommandRunner.cs:2454`). Since
every tutorial verifier reads the HOST, the roles are: **HOST = M5 windowed built player (the
driver), CLIENT = BEAST headless player (a background player agent)**. SSH form: put the logic in
a script file and run `ssh beast '"C:\Program Files\Git\bin\bash.exe" -lc "bash /c/Users/rydin/ff-worker/x.sh"'`
— cmd.exe mangles `|` and `\"` in an inline remote command. Newest session pid: list
`AppData/LocalLow/Never Games/finalfactory/AgentControl/session-*.json` by mtime. `GET help` on
Windows needs `PYTHONIOENCODING=utf-8`. A launch can exceed a 180 s tool timeout — background it.

**Pointer mapping (M5 host, `-screen-width 1280 -screen-height 800`).** Native coordinates are
2× the 1280×691 `screenshot?maxEdge=1280` shot with Y flipped: `native_y = 1382 − 2·shot_y`.
Hotbar: Space `pointer.moveto|1150|176|screen`, C `1216|176`, V `1280|176`; a world click at
`1400|782`; inventory slot 4 at `910|1018`. `pointer.moveto|<tileX>|<tileZ>` (no `screen`) projects
a TILE, which must land inside the game view.

**Placement route that works (item from inventory → built structure):** `ui.open|inventory` →
`pointer.moveto|<slot>|screen` + `pointer.click` (or `ui.click|inventory|InventoryPanel/Content/Inventory/item-slot(Clone)[item=Mining Station]`)
→ `ui.close|inventory` → `pointer.moveto|<tileX>|<tileZ>` → `pointer.click|0|3`. `construction.place`
takes an `ffblueprintstart` paste string, NOT an inventory item. Three blockers: a modal
("Technology Unlocked" — Dismiss first), an ARMED ability (`CanPlaceFromPointer` refuses; a
right-click clears it but also DROPS a held item — cancel abilities BEFORE selecting), and a tile
inside the asteroid footprint (red ghost, never commits; (-4,-58) worked beside the (-13,-58)
asteroid). Removal: `construction.remove|<x>|<z>` (networked UnbuildRequest, refunds the item).

**Config + verb facts.** A fresh world under the verification profile needs `AuditSaveName:
generated:<seed>` + `AuditSaveSha256: sha256("generated:<seed>")` (else `Audit save identity is
required`); a loaded save uses the save name + the zip's sha256 on BOTH peers, `SaveName` on the
host only. `TargetClientCount: 2` counts the host. Agent-channel saves must be prefixed
`claude_playtest_`. `movement.goto|<x>|<z>|<tol>|<timeout>` takes WORLD units (tile × 10).
`transfer.put|<item>|<n>|<x>|<z>` / `transfer.grab`, `fleettransfer.give|<ship>|<n>|<x>|<z>`,
`rotate.abs|<x>|<z>|<0-3>`, `craft.queue|<item>|<n>`, `research.queue|<tech>`. A chain result
carries only its LAST segment's result — one `observe.*` per chain.

**Desync signals on a client.** A client peer has none except the `epoch` field of `GET hello`
changing or the heartbeat going backwards; a host crash shows on the client as heartbeat FROZEN
while `frameCount` advances plus chains rejected with "requires PlayersManager.Me to be ready".
Checkpoint pairs: `checkpoint.py` on the host, `ffauto:audit.write|<label>` on the client, then
derive the shared (epoch, simulationTimeRaw) window and run `scripts/continuous_determinism_verdict.py
--start E:RAW --end E:RAW --players 2` (`scripts/audit/compare_determinism_reports.sh` cannot read
verification-profile reports). Companion: [[cross-platform-leg-staging-and-the-movers-position-residual]].
