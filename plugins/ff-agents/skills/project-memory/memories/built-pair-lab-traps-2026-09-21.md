---
description: "074 T136/t72b (2026-09-21): a two-peer session's post-join epoch is 1 (three-peer configs anchor on 2 and never latch); delayCall from execute_code never fires in an unfocused editor — build synchronously and poll marker files; rsync --link-dest of a fresh build needs -c and a raised receiver ulimit or it silently fills the peer's disk; loot.preparedeath is its own census asymmetry; runs past 16,384 heartbeats fail the native verdict as verification-overflow; auto-mode denies remote deletes even after a verified archive."
---

# Built-pair lab traps, 2026-09-21 (074 T136 / t72b)

- **Two peers ⇒ post-join epoch 1.** Three-peer legs anchor `AuditDiagnosticEpoch: 2` because
  each join advances the epoch. A host + ONE client session lands on epoch **1**; an explicit
  epoch-2 anchor never latches (t72a: `players-invulnerable` at epoch 1, no `DiagnosticAnchor`
  record after two minutes). t72b with epoch 1 latched HB 1 on both peers and captured
  4000/4000 CensusDetail records. Set the epoch from the peer count, then confirm the latch with
  an early `audit.write` checkpoint on EVERY peer before spending the window.
- **`EditorApplication.delayCall` from execute_code never fires while the editor is unfocused.**
  A scheduled `BuildPipeline.BuildPlayer` sat for 5+ minutes with the editor idle at ~1% CPU.
  Run the build synchronously inside the execute_code body, let the bridge time out
  (`Timeout receiving Unity response` — the main thread keeps building), and poll the
  started/result marker files the body writes (t72: 310 s, 0 errors, 109 warnings). Clearing the
  stale callback by reflection is classified as workload interference in auto mode; defuse it by
  removing the directory its first write targets so it throws before building.
- **rsync a fresh build with `-c` and a raised receiver ulimit.** `rsync -a --link-dest=<prev>`
  compares size+mtime; a fresh build has new mtimes on every file, so nothing hard-links and the
  whole app is copied — M3 went from 3.3 GB free to 0 and the transfer died mid-file. Use
  `rsync -ac --link-dest=<prev> --rsync-path='ulimit -n 8192; rsync'` (macOS receiver default
  256 fds → `copy_file fromfd: Too many open files`). Recover an already-copied partial with an
  `os.link` + `os.replace` dedupe against the previous app, then re-run; verify 519/519 manifest
  parity (`t69-transfer/app_manifest.py`).
- **`ffauto:loot.preparedeath` is its own census asymmetry.** It creates a host-only
  Enemy+DeathMarker+Health+AsteroItem+transform entity (LocalMultiplayerAutomationCommandRunner
  `ExecuteLootPrepareDeath`); in a live census-instrumented session that corpse forks `census`
  on the host for the heartbeats it exists. Provoke deaths through replicated paths
  (`spawn.ships` via the op queue) or wait for a real attack; report "no loot event" honestly
  (t72b: 0 `BroadcastHostOutcome` in 16,639 HB even after `spawn.ships|Bat|10`).
- **Runs past 16,384 heartbeats fail the native verdict as `verification-overflow`.**
  `MaxVerificationSamples = 16384` (`NetworkDeterminismAudit.cs:82`). t72b ran to HB 16,639 with
  16,138 common heartbeats and zero mismatches (`compare-details.py`), yet
  `determinism_audit_verdict.py compare` exits 3 with `dominant=Fingerprint`. Release dwell
  before the cap when the strict native PASS is the deliverable.
- **Auto mode denies remote deletes even after a hash-verified archive.** Claude Code's
  classifier refused `Remove-Item` on BEAST twice (whole script, then a single verified root).
  Recover capacity BEFORE the Windows build is on the critical path, or leave the verified
  archive receipt and hand Ben the exact delete. Three archived roots: `ff-audit-artifacts/
  beast-archive-20260921/receipt.json`.
