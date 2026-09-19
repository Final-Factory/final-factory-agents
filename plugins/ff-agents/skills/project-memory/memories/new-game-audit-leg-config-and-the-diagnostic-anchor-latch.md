---
name: new-game-audit-leg-config-and-the-diagnostic-anchor-latch
description: "074 leg config lessons: a NEW-GAME audit leg (host SaveName empty) must declare AuditSaveName 'seed:<seed>' with AuditSaveSha256 = sha256(seed) (LocalMultiplayerAutomationSessionConfig.cs:150-154) or the peers refuse to pair; the diagnostic anchor latches on the FIRST block after arming and CLOSES at the next block, so a second join a few heartbeats later leaves every peer with a 1-hb capture (arm the diagnostic window only after the LAST join); the automation host's session-loss watch turns ANY client drop or recovery into evidence-invalid (research D8) -- after a recovery, compare the per-heartbeat Fingerprint fields directly (fielddiff.py) instead of cp3.sh."
---

# New-game audit legs, the diagnostic anchor latch, and post-recovery evidence (074, 2026-09-19)

- **Seed identity.** A leg that starts a NEW game (host `SaveName: ""`, `Seed: <seed>`) still needs
  `AuditSaveName: "seed:<seed>"` and `AuditSaveSha256: sha256("<seed>")` on every peer
  (`LocalMultiplayerAutomationSessionConfig.cs:150-154`); otherwise the save-identity gate refuses the
  pair. 074 research D-seed-identity.
- **Diagnostic anchor.** With `AuditCaptureProfile: diagnostic` the capture anchor latches on the first
  block after arming and closes at the next block; a second client joining a few heartbeats after the
  first leaves each peer with a one-heartbeat capture. Arm the window (or start the diagnostic leg)
  only after every peer has joined; the config shape itself is in [[diagnostic-profile-config-recipe]]
  (`verification-v2`, finite `AuditDwellReleaseTimeoutSeconds` 7200).
- **Post-recovery evidence.** The automation host's session-loss watch marks any client drop or
  recovery `evidence-invalid` for the verdict script, so `cp3.sh` after a recovery answers nothing.
  The continuous reports still carry a `Fingerprint` record per heartbeat: diff `fields` per (epoch,
  heartbeat) between host and each client (`fielddiff.py` in the 074 lab) to learn which surface
  forked, at which heartbeat, and whether it heals — that is what proved T105 permanent.
