---
name: honest-coop-play
description: Run a sitting of Final Factory's HONEST three-player co-op game — Ben's standing goal (2026-09-22) that Claude beats the game with NO cheats, in ONE continuous game, with a distinct agent playing on each of the three machines (M5 host, M3 and BEAST clients) coordinating over a shared board. Use when resuming or continuing the honest playthrough (074 T145/T146), launching the next sitting, spawning the three play agents, ending a sitting, or checking that the game is still honest and continuous.
---

# honest-coop-play

**The goal (Ben, 2026-09-22):** "beat the game WITHOUT cheats … one continuous game", played as a
real three-player networked game with **a distinct agent on each machine**, coordinating so the
game goes faster. Binding record: `specs/074-three-peer-full-playthrough/spec.md` FR-010..FR-012 +
SC-007, tasks T144–T150; the current position is the newest dated SESSION HANDOFF in that
feature's `plan.md` plus the T145 line in `tasks.md`. Cheat-accelerated saves (`074-p1`..`074-p7-*`)
are determinism test fixtures only — they can never count toward this win.

## The rules that make it honest (all enforced, not trusted)

1. **No cheats.** Nothing created from nothing (items, ships, research points, unlocks), no
   teleport, no skipped cost/build-time/reach rule, no destroying outside play. Normal player
   actions driven by an agent are play.
2. **The guard is on every peer**: launch flag `-ffHonestPlay true` (never `-ffAgentControlDev`),
   and `"HonestPlay": true` in every config. Armed, the player clamps every command channel to the
   73-command honest set, holds transfers to the human reach, refuses the Quantum console, and
   **refuses to start** with `InvulnerablePlayers`, `DisableEnemyGeneration` or `FlatMap` set
   (status `honest-play-config-refused`). Every peer's log must show `honest-play-armed: allowed=73`.
   The flag also keeps the sitting's desync and crash reports off ffintake (game `c6f88fa99`): a
   peer missing it counts as a person playing and uploads them.
3. **One continuous game.** Sitting N+1 loads exactly sitting N's final host save; record the chain
   (save name + SHA-256) in the handoff. Honest saves are named `claude_playtest_074-h<N>-<slug>`
   (the guard confines `game.save` to that prefix). Only the host saves.
4. **Check honesty per sitting (SC-007):** `python3 <skill>/scripts/save-meta.py <save.zip>` must
   print `AchievementsLocked: False` for every save (the flag is live: one unguarded cheat on the
   same build flips it to True — T149a); zero cheats executed; seed SHA == previous final SHA.
5. A **recovery** (desync resync) keeps the game continuous — it is a bug to fix, not a restart.

## Play like a human: automate (Ben, 2026-09-23)
Winning honestly is not enough — play the way the game is meant to be played. Hand-crafting and hand-carrying
are bootstrap tools only; research bots, their inputs and fleet ships come from AUTOMATED lines (HowToPlay
§2b: Ship Assembler on the stations' logistics network, belts in, bots auto-route; players within ~60 tiles
steal assembler output). The briefs carry this rule; the driver corrects any agent that drifts back into
mass hand-crafting (h2–h3 hand-crafted several hundred research bots — the mistake this section exists for).
Agents also SEE the game: every peer runs windowed and screenshots regularly (step 3, briefs).

## Defence, fog and dialogs (Ben, h6, 2026-09-25)

- **Defence scales with the base.** Attacks scale with Global Signal AND base size/stability, so
  defence must grow as the base grows — every new production module gets Defense Platform cover.
  Watch the HUD attack/damage warnings every batch (`AttackWarningData` is NOT in `observe.state`
  alerts — screenshot instead). Full mechanics (signal formula, the Defense Platform
  blueprint-range trap, Exploration Center radius/slots/power) live in `docs/HowToPlay.md`
  "Defence and vision (074 h6)" (internal, code-traced) and the PUBLIC kit skills `defend-base`,
  `reveal-map`, `manage-stability-power` (`finalfactory-agent-kit` v0.1.1+, player-framed) — read
  those before re-deriving; don't duplicate their content here or in the briefs.
- **Dismiss dialogs like a player.** After every research completion, screenshot and dismiss any
  "Technology Unlocked" dialog through a real click, never a debug/skip channel —
  [[built-player-screenshot-coordinate-scale]] has the exact Mac Retina recipe (2x scale + Y-origin
  flip + a non-zero click hold).
- **`scripts/mkbp.py` blueprints place ranged structures at their MAXIMUM range** (074 T173, fixed
  2026-09-26): the sample item is a Dark Star Gate with range 0/0, which made every Defense Platform
  placed from an mkbp blueprint 0 m (it never fought). It now writes `AttackRange`/`AlertRange` 1e6 and the
  game clamps to each structure's config ceiling (`StructureRangeResolver.Clamp`). A platform placed
  from an OLD mkbp blueprint still needs its range set in its panel.

## Machines and lab

`E=/Users/benryding/nevergames/ff-audit-artifacts/074-20260921` (override with `FF_COOP_LAB`).
M5 = host (this Mac, windowed since h4). M3 = client, `ssh m3`, windowed, same `$E` paths.
BEAST = Windows client, `ssh -o Hostname=10.0.0.158 beast`, Git bash `"C:\Program Files\Git\bin\bash.exe" -lc`
(cannot carry `|` — scp a script and run it). **BEAST work runs inside an ffsb sandbox** (Ben 2026-09-23;
project-memory `feedback-beast-work-goes-through-a-sandbox`): `mcp__ffsb__create_sandbox`, then build and run the
player from `F:/ffsb/<name>/Builds/<leg>/`. `C:/Users/rydin/ff-worker` is the legacy lab — don't add to it. Clients join the host's
Tailscale address `100.80.111.95`. Matching built players on all three (Mac `.app` on M5 and M3,
Windows build on BEAST) at the same source sha.

## Sitting lifecycle

1. **Players.** If code changed since the last sitting, rebuild both (editor-ops / 074 plan recipe):
   Mac in-editor `BuildPipeline.BuildPlayer` (Development) **after force-reimporting
   `Assets/Scenes/main/EntitySubScene.unity`** — otherwise the build "succeeds" with only
   `scene_info.bin` under EntityScenes and the host hangs at the title menu. Do the reimport and the
   `BuildPlayer` in SEPARATE editor calls: in ONE `execute_code` call the build races the entity bake and
   still ships only `scene_info.bin` (2026-09-23 MP beta build, first attempt); Windows via Git-bundle
   sync + `build-win-<tag>.sh`. Verify: `.entityheader` + `.0.entities` present on both, and
   `python3 <skill>/scripts/symcheck.py <FFSpaghetti.dll> <new symbol>` equal on both. Mirror the
   Mac player to M3 with `rsync -ac --link-dest=<prev player>/ --rsync-path='ulimit -n 8192; rsync'`
   and check file-count parity.
2. **Configs.** `python3 <skill>/scripts/derive-sitting.py <prev-leg> <new-leg> <sha40> <mac-player-dir>
   <beast-build-dir> <seed-save> <seed-sha256> <port>` in `$E` (refuses to overwrite and refuses a
   non-honest config). Stage `m3-<leg>.sh`, `client-config-<leg>-m3.json`, `release-<leg>.py` on M3
   and `beast-client-<leg>.sh`, `client-config-<leg>-beast.json`, `beast-release-<leg>.sh` on BEAST.
   The seed save must be in the HOST's Saves folder.
3. **Launch, in order — every peer WINDOWED** so agents can screenshot (from h4). Exception: when M5's session is
   LOCKED (nights), a windowed host gets no frames and hangs at `waiting-title-menu` — run it `-batchmode -nographics`
   instead, and plan for ~3 h: a headless player leaks FMOD `Ambience.bank` handles until its agent channel dies
   (074 T176; the sim and autosaves keep going, so end the sitting from an autosave). `derive-sitting.py`
   copies the previous launch lines, so check `host-<leg>.sh` and `beast-client-<leg>.sh` use
   `-screen-fullscreen 0 -screen-width 1280 -screen-height 720`, not `-batchmode -nographics` (M3 always has).
   Host `(nohup bash host-<leg>.sh > host-<leg>.out 2>&1 &)`, wait for `status waiting-host-peers-connected`.
   BEAST must start in its logged-in DESKTOP session (an ssh-started process lands in session 0, "Services",
   with no desktop): copy `$E/beast-launch-h4-desktop.cmd` to `beast-launch-<leg>-desktop.cmd` with the
   leg renamed (it runs `schtasks /create … /it /f` + `schtasks /run` on `beast-client-<leg>.sh`, then
   `schtasks /delete /tn <task> /f` — a `/sc once /st 23:59` task left behind RE-FIRES at 23:59 BEAST time and
   launches a second client that reclaims the slot, h8 2026-09-26), scp it to
   `C:\Users\rydin\ff-worker\`, run it over ssh, and confirm `tasklist /V` shows the player in session
   `Console` (needs rydin logged in on BEAST: `query user`). Then `ssh m3 "bash $E/m3-<leg>.sh"`.
   Wait for `host-peers-connected: connectedClients=3` and `waiting-audit-dwell-release`
   (dwell timeout 0 = unlimited). Check `honest-play-armed` on all three.
4. **Bridge.** Deploy `scripts/ahttp.py` to `$E/` (M5, M3) and `C:\Users\rydin\ff-worker\ahttp.py`
   (BEAST); copy `scripts/peer.sh` to `$E/`; write the three player pids to `$E/peer-pid-{host,m3,beast}`.
   `peer.sh <peer> GET hello` must report `"tier":"honest"` for all three.
5. **Board.** Start `$E/coop-board.md` from `references/coop-board-template.md`, carrying over the
   previous board's still-valid claims, requests and team goal.
6. **Agents — three, one per machine** (direct children, general-purpose on `opus`, background):
   fill `references/brief-host.md`, `brief-m3.md`, `brief-beast.md` (`<LEG>`, `<HOURS>`, `$E`) and spawn
   them together. The driver does not play; it watches, adjudicates findings and owns fixes.
7. **Watch.** One Monitor on `$E/host-terminal-<leg>.log` for `divergedSurfaces|DesyncRecovery|kicked|status error|won the game`
   plus a 10-minute progress line (objectives via `peer.sh host GET snapshot/objectives`); re-arm
   every 30 minutes. A desync stops all three agents: diagnose it (determinism-audit skill; the
   host's `desyncReports/*.txt` + a per-epoch Fingerprint diff of the checkpoints name the surface
   and heartbeats), fix it RED→GREEN, rebuild, continue from the last save in a new sitting.
8. **End the sitting.** Host agent writes its final save → driver copies it to `$E` with its SHA and
   runs `save-meta.py` → checkpoint ALL THREE before stopping anything (`scripts/checkpoint.py <pid>
   <host|client> <label>` from `$E` on M5 and on M3 — it needs `agent_http.py` beside it;
   `python scripts/beast-checkpoint.py <pid> <label>` in `C:\Users\rydin\ff-worker` on BEAST — it needs
   `agent_http_win.py` beside it; scp the printed report path back with forward slashes) → release
   (`release-<leg>.py` on M5 and M3, `beast-release-<leg>.sh` on BEAST) → wait for `report-written`
   → copy finals + SHA256SUMS → stop each player by verified pid (`ps` / `taskkill`) → remove
   `.ff-local-automation.json` and the release gates → `python3 scripts/fingerprint-compare.py <dir>` per epoch (the strict
   verdict script calls any report containing a desync evidence-invalid, correctly) → record
   T145/T146 (leg, players sha, seed and final save + SHAs, honesty check, findings) and commit.

## Context handoff WITHOUT ending the sitting (the default between context windows)

The players are separate processes on the three machines; restarting Claude kills only the play
AGENTS (subagents of the driver session), never the game. So a context handoff keeps the sitting
LIVE and the next session respawns the agents into the same game:

1. **Wind down** (old session): message all three agents to finish their current action, leave
   their player idle (no chain running), post a status line on the board and update their notes
   file; the host also writes a checkpoint save `claude_playtest_074-<leg>-<slug>`. Wait for all
   three final reports — Ben must not restart while an agent is mid-action.
2. **Evidence**: `save-meta.py` on the new saves (all `AchievementsLocked: False`), checkpoint all
   three peers WITHOUT releasing (`checkpoint.py` / `beast-checkpoint.py`), `fingerprint-compare.py`
   on them. Leave the players, configs and gates in place.
3. **Handoff** (`/ff-agents:handoff`): the handoff header and `local-handoff.md` name the live leg,
   the three pids (also in `$E/peer-pid-*`), the board, the notes files, the last save + SHA, and
   the resume steps below.
4. **Resume** (new session, after `/ff-agents:resumeFromHandoff`): `$E/sitting-health.sh <leg>`
   (exit 0 = all three alive, tier honest, 3 clients connected, 0 verdicts). If healthy: re-read the
   board and the three notes files, update the board's team goal, re-arm the Monitor (step 7), then
   spawn the three agents with the role briefs (step 6) — they continue the same game. If NOT
   healthy (a player died, a machine rebooted, a desync): end the sitting (step 8), fix if needed,
   and start the next sitting from the last save.

End the sitting (step 8) instead only when the players themselves must restart: a rebuild after a
fix, a reboot, or a long break.

## Agent hygiene learned in h2

- **Each agent keeps its helper scripts in its OWN folder** (`<scratchpad>/<role>/`). In h2 the
  beast agent overwrote the host agent's `r.py` in the shared scratchpad and one host chain ran on
  BEAST. The briefs name the folder; the driver never shares one.
- **A client can join DEAD** (health 0, can't move; `movement.goto` still reports success and
  `mining.until` silently mines nothing). Every client agent's first action: `snapshot/player`; if
  health is 0, `ffauto:combat.respawn`.
- A client player starts with its own near-empty inventory and NO construction bots: its placed
  ghosts stay frames ("no construction bots") until it crafts one (4 AI Controller Circuit + 2
  Plasma Engine Parts).
- Mass-driver targets have no verb: select the driver, click SetTarget, click the destination (UI).
- Research: the host refuses to queue a tech whose prerequisite is only queued, not researched.
- `ahttp.py` writes raw bytes: `peer.sh m3 GET screenshot > m3.png` works (M3 is windowed; the
  headless peers return `no_frame_available`).

## Traps already paid for

- A relaunch after a failed launch needs a **new leg id**: the aborted attempt already published a
  report under the old id and the final write fails with "Audit artifact identity collision".
- A new-game audit needs `AuditSaveName: "seed:<seed>"` + `AuditSaveSha256 = sha256(<seed>)`.
- `heartbeats`, `inventory.add`, `spawn.ships`, `player.setposition`, `craft.ship`, `ability.cast`,
  `blueprint.place`, `enemy.dumpcamps` are refused under the guard — by design.
- Holding a blueprint over the grid used to fork the census (T147, fixed in `3f3b7a4a3`); an inserter
  could not be placed by `construction.place` until T148 (`dcdea8adf`). Players older than
  `dcdea8adf` must not be used for honest sittings.
- After a load, `snapshot/objectives` can report a lower `completedCount` than the live game did
  (T150); the current objective is what matters.
- Never print a whole audit detail line; never run local pairs with GB-scale captures beside the editor.
