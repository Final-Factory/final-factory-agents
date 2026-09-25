---
name: feedback-beast-work-goes-through-a-sandbox
description: Ben 2026-09-23 — any work on BEAST (builds, test-leg clients, play agents, editors) runs inside an ffsb sandbox, never in BEAST's own checkout or C:/Users/rydin/ff-worker; sandboxes are a standing pool of 4 that new work REUSES by switching branch (never create per feature, never tear down); mp-r2 is reserved for MP tests; label a sandbox with set_label when taking it, `unused` when done
metadata:
  type: feedback
---

**Rule (Ben, 2026-09-23, binding):** when a task needs BEAST for anything — a Windows build, a
multiplayer test-leg client, an honest-coop play client, an editor, a worker agent — spin up an
**ffsb sandbox** and work inside it. Do not build in `C:/Users/rydin/nevergames/FinalFactory` or
run players from `C:/Users/rydin/ff-worker` any more; those are the pre-sandbox lab and are legacy.

**Exception, builds that go to Steam (Ben, 2026-09-25):** never made on BEAST, sandbox or not.
Releases (main and demo) are built and uploaded by CI on ffbox (`ci-release`); MP beta builds are made
on the M5, which builds both the PC and the Mac versions (`mp-beta-deploy`, `steam-upload`). Sandbox
Windows builds are for test legs and play clients only.

**Why:** the sandbox system (the `ffsb` MCP server, orchestrator on BEAST) owns BEAST's disk,
editors and agents: it gives each job its own git worktree + branch + warm Library, enforces the
editor/agent caps (`system_status`: 3 editors, 6 agents), and shows everything on one dashboard.
Ad-hoc work in the old checkout collides with it and is invisible to it.

**Standing pool — reuse, don't churn (Ben, 2026-09-23, binding):**
- Keep **4 sandboxes up at all times** (as of 2026-09-23: `mp-r2`, `shader-blackhole`, `agent-mcp`,
  `blackhole-master`).
- **`mp-r2` is Ben's permanent multiplayer-test sandbox**: reserved for MP testing, never repurposed
  for other work. The **general pool** is the others (currently `shader-blackhole`, `agent-mcp`,
  `blackhole-master`); their names are historical and any idle one can take any work.
- **Labels show Ben what each sandbox is for.** Idle means labelled exactly `unused` AND no running
  agent. A worker relabels its OWN sandbox with `mcp__sandbox__set_label {purpose}`; the orchestrator
  (and `mcp__ffsb__*` remote clients) use `set_sandbox_label {sandbox, purpose}`. Either changes the
  label only, never the folder, worktree, branch or Unity project name.
- Never create a sandbox per feature and never tear one down when work finishes. **Never
  `delete_sandbox` unless Ben explicitly asked** (the tool itself requires `ben_asked: true`).
- New work (feature, fix, playtest, anything) goes to a general-pool sandbox with **no running
  agent** (`list_sandboxes`), preferring ones labelled `unused`, then one whose editor is already up if the task needs Unity (cap: 3
  editors, 6 agents). Only if all are busy, **ask Ben first**, then create one.
- **Why:** a fresh sandbox's first Unity import takes very long; an existing one's Library and editor
  are warm, and a branch switch reimports only what differs.
- **Switching a sandbox is the worker's first step:**
  1. `git status` must be clean. If not, STOP and ask Ben — never stash or discard earlier work.
  2. Push the old branch if it has unpushed commits.
  3. `git fetch`, then `git switch <existing-branch>` or `git switch -c NNN-short-name origin/develop`.
     A branch can be checked out in only one worktree at a time. **In the same step, set the label**
     to a short description of the task: `mcp__sandbox__set_label {purpose: "074 T160 Relay join fix"}`.
  4. Wait for the editor to finish reimport + compile before using it.
- **When done with the sandbox** (work pushed, nothing left running), set the label to exactly
  `unused`: `mcp__sandbox__set_label {purpose: "unused"}`. That is what returns it to the pool.
- The dashboard's *branch* field can go stale after a switch; `git` in the worktree is the truth.
- The label tools came with ff-sandboxes commit `dc230a0` (branch `sandbox-labels`, 2026-09-23); a server not yet updated
  and restarted lacks them. If `set_label` is missing, say so in your report rather than skipping.
- **Waiting inside a worker:** ONE foreground Bash polling loop (up to ~10 min) on a real condition,
  e.g. `for i in $(seq 1 30); do grep -q "Reloading assemblies after successful compilation"
  Logs/sandbox-editor.log && break; sleep 20; done`, or poll `mcp__sandbox__unity` status. A
  standalone `sleep` is blocked, and Monitor/background tasks never wake a worker whose turn ended.
- **Pushing from a sandbox (Ben, 2026-09-23):** only the **Final Factory game repo's** master/main is
  off-limits (no push, no PR into it). Other repos' master/main (final-factory-agents via
  publish-skills, ff-sandboxes) are fine when that is their normal flow. Force pushes, remote-branch
  deletion and `--mirror`/`--all` stay blocked in every repo. The worker guard enforces this from
  ff-sandboxes commit `f598184`; it reads the target from the remote URL and blocks when unsure.

**How to apply:**
- Tools: `mcp__ffsb__*` (load via ToolSearch `select:`). `list_sandboxes` first and reuse an idle
  pool sandbox (above). Creating one (only with Ben's OK): `create_sandbox(name, purpose,
  base=origin/develop or the exact sha's branch, seed_library=true, start_unity=<only if an editor
  is needed>)`. It returns at once;
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
- **Moving an existing sandbox to a newer commit: bundle it, never `git fetch` over ssh.** An
  ssh-run `git fetch origin` in the sandbox has no GitHub credentials (session 0: "Unable to persist
  credentials with the 'wincredman' credential store") and then hangs forever at a `git-askpass`
  username prompt. On M5: `git branch -f tmp <sha>; git bundle create x.bundle <sandbox-HEAD>..tmp`,
  scp it into `Builds/`, then in the sandbox `git fetch <bundle> refs/heads/tmp:refs/remotes/origin/x
  && git merge --ff-only refs/remotes/origin/x`. Kill only YOUR hung fetch, identified by its
  command line (`Get-CimInstance Win32_Process` from a scp'd .ps1 — inline quoting breaks over ssh).
  A rebuild in an already-built sandbox is fast: prepare ~40 s + build ~2.5 min (r3, 2026-09-24).
- **Counting lines in a multi-GB BEAST player log:** never `find /c` or `findstr` over ssh. `findstr`
  aborts on long lines ("Line N is too long"), and `find /c` stalled for 10+ minutes AND kept the
  log locked after the M5 side was stopped, so the delete failed. Run `LC_ALL=C grep -E … | cut`
  from a scp'd Git-bash script instead (seconds), and kill any leftover `find.exe` by command line.
- Sandbox worker agents (`start_agent`) did not have the Unity MCP tools as of 2026-09-23, so the
  M5 driver runs BEAST builds and players itself over ssh inside the sandbox folder.

Related: [[beast-sandbox-editor-driven-from-m5]] (driving a sandbox editor without MCP; the FMOD
modal freeze), [[headless-windows-player-over-ssh-and-placement-route]],
[[live-mp-repro-harness-notes-2026-09-23]], [[three-peer-lane-recipe-and-traps]].
