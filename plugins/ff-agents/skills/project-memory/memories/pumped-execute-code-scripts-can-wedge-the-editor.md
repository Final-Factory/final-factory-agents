---
name: pumped-execute-code-scripts-can-wedge-the-editor
description: "Two execute_code scripts that pumped EditorApplication.Step() for long stretches after LoadGame (one polling ffauto:waituntil/wait.status, one a 60-s until-running loop) left the main editor's main thread spinning in managed code under a reflected invoke — bridge 'Command TCS timed out (N consecutive)', ~330% CPU, stale status heartbeat, unity CLI hung too. Keep execute_code calls under ~40 s / ≤300 Steps, poll ECS state directly, never waituntil through TryExecute; sample the main thread, then path-verified kill + scripts/launch-editor.sh."
---

# Pumped `execute_code` scripts can wedge the editor (074, 2026-09-19)

**What happened, twice.** After `SaveGameManager.LoadGame(...)` from `execute_code`, a script that
pumped `EditorApplication.Step()` for a long stretch never returned: the bridge call timed out
client-side (~2 min, normal), but then EVERY later call timed out too, the on-disk log showed
`MCP-FOR-UNITY: Command TCS timed out (N consecutive)`, `~/.unity-mcp/unity-mcp-status-<hash>.json`
`last_heartbeat` went stale for minutes, the editor sat at ~330 % CPU and `~/.local/bin/unity
editor_status` hung as well (both channels need the main thread). `sample <pid> 3 -mayDie` showed
the main thread inside `__NSFireTimer → mono_runtime_invoke → … InternalInvoke` (the Roslyn-compiled
script) in a getcwd-hot managed loop. First script: `research.queue`/`research.setactive` then
`ffauto:waituntil|objectiveComplete|…` with `wait.status` polling between Step batches. Second: a
60-s "pump until GameStarted && MePlayer && hb > 40" loop, after which even a trivial query script
hung. `wait.status` itself is harmless (`ExecuteWaitStatus`, CommandRunner ~4490); the exact spin
was not isolated. The earlier probes that WORKED on the same editor used ≤ 34 Steps to reach
"running" (14 s) and ≤ 350 Steps (3 s) per call.

**Prevention.** One `execute_code` call = one bounded unit: < ~40 s wall, ≤ 300 Steps, then return
state and decide in the driver. Poll ECS state directly (`EntityQuery` counts, `Heartbeat`,
`GameMetaState`) between calls; never `ffauto:waituntil` through
`LocalMultiplayerAutomationCommandRunner.TryExecute` (that verb is for the chain runner / HTTP
path). Use the synchronous verbs (`construction.place`, `craft.queue`, `research.*`) and pump a
fixed small batch after each.

**Recovery (authorized by CLAUDE.md, no user intervention).** Sample first so the restart is
evidence-based, then: `ps -p <pid> -o command=` must show `-projectPath <this checkout>` (never the
clone, never Unity Hub); `kill -TERM <pid>` and its `-parentPid <pid>` AssetImportWorkers; poll
`ps -axo pid,command | grep -c "[M]acOS/Unity -projectPath <path>$"` to ZERO; relaunch ONLY through
the game repo's `scripts/launch-editor.sh` (clears `Temp/__Backupscenes`, the stale
`Temp/UnityLockfile`, `Library/LastSceneManagerSetup.txt`, refuses a double launch); it opens NO
scene, so after the bridge registers: pin by port, `EditorSceneManager.OpenScene(
"Assets/Scenes/main.unity")` via `execute_code`, then play. Boot to bridge-ready took under a minute.
