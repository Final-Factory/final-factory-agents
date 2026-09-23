---
name: feedback-beast-work-goes-through-a-sandbox
description: Ben 2026-09-23 — any work on BEAST (builds, test-leg clients, play agents, editors) runs inside an ffsb sandbox created through the ffsb MCP, never in BEAST's own checkout or C:/Users/rydin/ff-worker
metadata:
  type: feedback
---

**Rule (Ben, 2026-09-23, binding):** when a task needs BEAST for anything — a Windows build, a
multiplayer test-leg client, an honest-coop play client, an editor, a worker agent — spin up an
**ffsb sandbox** and work inside it. Do not build in `C:/Users/rydin/nevergames/FinalFactory` or
run players from `C:/Users/rydin/ff-worker` any more; those are the pre-sandbox lab and are legacy.

**Why:** the sandbox system (the `ffsb` MCP server, orchestrator on BEAST) owns BEAST's disk,
editors and agents: it gives each job its own git worktree + branch + warm Library, enforces the
editor/agent caps (`system_status`: 3 editors, 6 agents), and shows everything on one dashboard.
Ad-hoc work in the old checkout collides with it and is invisible to it.

**How to apply:**
- Tools: `mcp__ffsb__*` (load via ToolSearch `select:`). `list_sandboxes` first — reuse one whose
  purpose matches; else `create_sandbox(name, purpose, base=origin/develop or the exact sha's
  branch, seed_library=true, start_unity=<only if an editor is needed>)`. It returns at once;
  provisioning (checkout, then a ~60+ GB warm Library copy, several minutes) runs in the
  background — wait for `list_sandboxes` to show it ready before a batchmode build.
- **Sandbox root is `F:\ffsb\<name>`** (bash `/f/ffsb/<name>`), NOT `C:\ffsb` as the orchestrator
  once claimed — trust the `create_sandbox` reply. Reachable over the usual
  `ssh -o Hostname=10.0.0.158 beast` + Git bash, so the existing M5-driven leg scripts keep working
  with paths swapped.
- Put build output, configs, logs and helpers (`ahttp.py`) under the sandbox's gitignored
  `Builds/<leg>/` so nothing dirties the worktree.
- A batchmode build (`PrepareWindowsMultiplayerBuild` then `BuildWindowsMultiplayerDev`) needs the
  sandbox's editor STOPPED (Unity project lock) — create it with `start_unity=false`, or
  `unity(action=stop)` first.
- **Proven recipe (074 leg r2, 2026-09-23; scripts in the 074 lab
  `E=/Users/benryding/nevergames/ff-audit-artifacts/074-20260921`):**
  1. `create_sandbox(name, purpose, base=origin/develop, seed_library=true, start_unity=false)` —
     ~4 min to `ready` (checkout, then a ~60 GB Library copy).
  2. scp `$E/sandbox-build-r2.sh` (retarget its `PROJECT`/`OUT`) into `F:/ffsb/<name>/Builds/<leg>/`
     and start it detached: `ssh -n … '"C:\Program Files\Git\bin\bash.exe" -lc "cd … && (nohup bash
     sandbox-build-r2.sh <40-hex sha> > build.out 2>&1 < /dev/null &)"'`. It refuses a HEAD mismatch
     or an editor lock. First build in a fresh sandbox: prepare ~5 min + build ~12 min.
  3. Verify before trusting it: `build-status.txt` ends `done`, and `StreamingAssets/EntityScenes`
     holds the `.entities` + `.entityheader` + `scene_info.bin` trio at the same size as a known-good
     build (the ships-only-`scene_info.bin` trap).
  4. Copy `ahttp.py` into the same `Builds/<leg>/` folder; `$E/peer.sh` reads its BEAST path from
     `FF_BEAST_AHTTP` (e.g. `F:/ffsb/<name>/Builds/<leg>/ahttp.py`). Launch with `$E/beast-client-r2.sh`
     (headless `-batchmode -nographics`, config copied beside the exe); pid from `tasklist`.
  A windowed honest-coop client still has to start in rydin's desktop session (see honest-coop-play);
  only the build/run location changes.
- Sandbox worker agents (`start_agent`) did not have the Unity MCP tools as of 2026-09-23, so the
  M5 driver runs BEAST builds and players itself over ssh inside the sandbox folder.
- Never `delete_sandbox` unless Ben asked; the tool itself requires `ben_asked: true`.

Related: [[headless-windows-player-over-ssh-and-placement-route]],
[[live-mp-repro-harness-notes-2026-09-23]], [[three-peer-lane-recipe-and-traps]].
