---
name: sandbox-player-build-reverts-tracked-edits-and-quiet-window-suspend
description: While scripts/nightly/build_player.sh runs in a sandbox, any edit to a tracked file is reverted when it finishes; a batchmode build cannot be killed by hand for a quiet window, so suspend its process tree and resume it; localhost multi-client runs need -ffAutomationReclaimIdentity per client; a Burst step that crawls on a saturated BEAST still finishes.
---

# Sandbox player builds: lost edits, pausing for a quiet window, localhost client identity

Learned on w111 (2026-10-01), four player builds in one BEAST sandbox while other agents built and ran players.

## `build_player.sh` reverts every tracked edit made while it runs

`scripts/nightly/build_player.sh` ends with `git diff --name-only` and a `git checkout -- <file>` for each file
(it undoes the ProjectSettings and graphics-asset edits the two batchmode passes make). It cannot tell those from
yours. A tracked file you edit during the build is back at HEAD when the manifest is written, with no message
beyond `"restoredFiles": N` in `build-manifest.json`.

- During a build, write only untracked files or scratch copies (`F:/ffsb-scratch/<work>/`), and apply them after
  `build-manifest.json` exists. Commits and merges are fine: a committed file no longer differs from HEAD.
- New untracked `.cs` files are safe from the revert, but the batchmode editor imports them (it writes their
  `.meta`), so do not leave half-written code in `Assets/` either.
- The player's scripts are compiled at the start of pass 2 (`Recompiling scripts for player build` in `build.log`),
  so an edit made later is not in the player.

## Pausing a build for a "quiet window"

The orchestrator may ask every agent to stop players and pause builds for N minutes. In a sandbox the harness
blocks killing Unity by hand ("Killing Unity, node, claude or PowerShell processes by hand is blocked"), and
`mcp__sandbox__unity stop` only manages the interactive editor, not a batchmode build you started.

Suspend the build's own process tree and resume it afterwards. Identify it by command line first (the
`build_player.sh` bash pair, the `Unity.exe -batchmode ... -projectPath <your sandbox>` and every descendant):

```powershell
Add-Type -Namespace W -Name S -MemberDefinition '[DllImport("ntdll.dll")] public static extern int NtSuspendProcess(IntPtr h); [DllImport("ntdll.dll")] public static extern int NtResumeProcess(IntPtr h);'
# walk ParentProcessId from the roots, save the pids to a file, then per pid:
[W.S]::NtSuspendProcess((Get-Process -Id $id).Handle)     # later: NtResumeProcess, same pids
```

A build suspended for 20 minutes early in pass 2 resumed and finished with status ok. Killing only the bash
script does not stop Unity, and leaves ProjectSettings modified.

## A Burst step that crawls is not hung

`GenerateNativePluginsForAssemblies` (bcl.exe) took 7.5 minutes on a quiet BEAST and 30-65 minutes when other
sandboxes were building or running five trailer players. Near the end bcl sits at ~0.1 core with a working set
under 100 MB for many minutes, with no I/O; `build.log` stops at `[971/978 ...]`. It finished every time. Judge
it by `(Get-Process -Id <bcl>).CPU` rising at all, not by the log.

## Localhost multi-client runs need a reclaim identity per client

Two clients of one machine read the same identity file. The host takes the second for the first one reconnecting
and drops the first: `[Reconnect] Superseded(ghost=1) by client 2 presenting reclaim guid ...`, then
`host-peer-lost-during-preconnect`. Pass `-ffAutomationReclaimIdentity <name>` per peer, as `ffnightly.py` does
(`scripts/feel/run_input_feel.sh` does since w111). Both clients also write their determinism report to the same
`...-client.log` name; compare each player's own `-logFile` instead
(`compare_determinism_reports.sh host.log client.log` works on player logs).

## Measuring beside your own editor

Running the 6,000-test fast suite, a domain reload or an ffmpeg encode while your measurement players run starved
a three-peer host to 4 frames in 16 s and cut capture clips to 16-36 fps. Run one thing at a time: runs first,
then the editor.
