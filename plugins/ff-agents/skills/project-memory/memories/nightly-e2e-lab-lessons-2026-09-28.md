---
name: nightly-e2e-lab-lessons-2026-09-28
description: "What the first three-player nightly e2e runs of built players on the M3 taught (075, 2026-09-28): the desync log line is not an oracle, the report files are; hosts end the session on the first disconnect unless -ffAutomationOutlivePairBreak; a real late join needs a smaller host target; late-joiner skips do not reproduce on loopback; BuildPlayer deletes its output's parent; an APFS repo clone diverges GBs per old build; the M3's Unity license lapsed; chains cap at 64 segments."
metadata:
  type: project
---

Source: the 075 nightly lane (`scripts/nightly/`, `specs/075-nightly-e2e-regression/research.md`), built
players launched with the automation command-line flags and driven over the 068 agent channel.

- **The desync log line is not an oracle.** `[DesyncDetector] Multiplayer desync detected` is written when the
  verdict notification drains, and a verdict that starts a 019 auto-recovery is wiped before it drains. An
  injected divergence produced no log line at all. The reliable signal is a new file in
  `<persistentDataPath>/desyncReports/*.txt` (its `divergedSurfaces=` line), written on receipt
  (`RuntimeDesyncDetectorSystem.WriteReportOnReceipt`). Keep a canary scenario that runs `ffauto:desync.inject`
  and must see a report; otherwise a dead oracle turns every "no desync" check green.
- **Hosts end the session on the first disconnect.** A built automation host logs `session-ended: client
  disconnected from host` and AutoQuits the moment any client leaves, so `net.rejoin`/`net.dropreconnect` has
  nothing to come back to. Pass `-ffAutomationOutlivePairBreak true` (300 s ceiling from the first break) on
  every peer. With no determinism audit, also pass `-ffAutomationWriteReport false` (else `report-error`).
- **A real late join needs a smaller host target.** With every peer in `-ffAutomationTargetClients`, the
  bootstrap waits for all of them and serves the world to all clients together, so nobody joins a running
  game. Give the host and the first clients the count present at start; launch the joiner mid-game.
- **Late-joiner skips (d9494b683, c59000002) do not go RED on loopback.** On one machine the joiner's
  controller reaches earlier clients before the `PlayerJoined` op, so they link it and apply its ops
  (checked at ea34aebcb: inventory, chest, colour, unbuild, plasma cast all applied on the bystander). Try
  send-delay shaping or a cross-machine peer before calling such a scenario a proof.
- **`LocalMultiplayerVerificationBuild.BuildPlayer` deletes its output's PARENT folder**
  (`LocalMultiplayerVerificationBuild.cs:131-134`). Put the player in its own subfolder or logs beside it vanish.
- **An APFS clone of the repo is free only at first.** `cp -cR` of the game checkout (69 GB Library) takes 36 s
  and ~2 GB, but every build of an older commit rewrites Library caches on either side and costs 3-5 GB of
  unshared blocks; the M3 went from 18 GB to 0.6 GB free. An editor + a batchmode build + three players also
  pushed swap to 5 GB. Delete builds after each run and watch `df`.
- **The M3's Unity license lapsed on 2026-09-28** (`LicenseGroupOfflineValidityPeriodIsExpired`, `Token not
  found in cache` in `~/Library/Logs/Unity/Unity.Licensing.Client.log`). `Unity.Licensing.Client
  --showEntitlements` prints "No licenses were found"; only a Unity Hub sign-in fixes it. Check it before a
  build rather than reading a generic batchmode failure.
- Small traps: an `ffauto` chain holds at most 64 segments; editing a bash script while bash runs it corrupts
  the running copy (a build failed with "uildOutput: command not found").

Related: [[three-peer-lane-recipe-and-traps]], [[live-mp-repro-harness-notes-2026-09-23]],
[[feedback-beast-work-goes-through-a-sandbox]].
