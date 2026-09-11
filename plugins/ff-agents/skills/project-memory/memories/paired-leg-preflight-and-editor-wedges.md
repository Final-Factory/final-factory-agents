---
name: paired-leg-preflight-and-editor-wedges
description: "Before any paired editor leg both editors must pass editor-preflight.sh (Burst enabled+drained); the four wedges a skipped preflight or a pulled scene produced on 2026-09-11 and their exact recoveries."
---

# Paired-leg preflight and the editor wedges it prevents (2026-09-11, 069 lane)

**Rule:** run `sh scripts/editor-preflight.sh <projectPath>` on the host AND the clone until both
print `preflight-pass` (Burst enabled + compilation drained) before writing any
`.ff-local-automation.json`. The automation launcher leaves
`BurstCompiler.Options.EnableBurstCompilation` **persistently false** after every leg, so
re-enable it first (eval `Unity.Burst.BurstCompiler.Options.EnableBurstCompilation = true;` via
`scripts/unity-cli.sh command --project-path <p> eval_file file=<snippet>`), then preflight.

What skipping it cost, each seen once:

- **SIGBUS crash** of the host editor: a leg launched right after a compile ran a managed
  `MirrorRailJob` while Burst was still compiling. Relaunch with `scripts/launch-editor.sh`.
- **"Ecs has no live World"**: launched right after a domain reload, the host entered play with
  no World — phase stuck at `editor-launcher-loaded`, client stuck at `joining-localhost`.
  Recovery: `EditorApplication.isPlaying = false` via eval_file on both, delete both configs,
  relaunch the leg.
- **Native "scene changed on disk" modal**: a `git pull`/fast-forward that rewrote
  `Assets/Scenes/main.unity` under the running editor (a scope=all refresh triggered it) blocks
  the editor on a native dialog no tool can dismiss. Kill the PID whose `-projectPath` you
  verified, `scripts/launch-editor.sh`, reopen the scene via eval_file.
- **Client written on a timer** races the host: write the client config only after the host's
  `.ff-local-automation-status.json` shows `waiting-host-peers-connected` with an mtime newer
  than the moment you wrote the host config (a stale status file from the previous leg says
  the same words).

Two config facts for rejoin (park + reclaim) legs: the host needs `"OutlivePairBreak": true`
or `net.leave` ends the session; the clone editor reads
`reclaim-identity-editor-<hash>.txt` and `ClientReclaimIdentity` caches it, so an identity
override must go through `OverrideForSession` (restore the files afterwards).
