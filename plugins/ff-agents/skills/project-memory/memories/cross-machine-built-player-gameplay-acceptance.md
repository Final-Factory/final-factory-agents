---
description: "Multiplayer gameplay fixes require matching current built players on two physical machines, with both peers driven through the reported sequence and visually inspected; editor tests and scripted audits support this gate but do not replace it."
---

# Cross-machine built-player gameplay acceptance

A multiplayer gameplay fix is not finished after unit tests, EditMode tests, two editors on one
machine, or a headless audit. Run matching current built players on two physical machines. Include
Windows and macOS when the affected path can differ by platform. Assign the other peer to a direct
child or another explicitly coordinated agent so both players are observed and driven throughout
the same run.

Replay the reported sequence through real player input. For a fresh-join defect, start with a new
world and join without issuing any gameplay command, then add movement, the actual developer-console
step if the report used it, miners, and recovery or rejoin when those paths are relevant. Keep each
phase separate enough to identify the first bad heartbeat. Unit, editor, persistent-testcase, and
automation audits complement this run; none substitutes for it.

Capture both peers at the same milestones. Open every screenshot with the runtime's image-inspection
tool and record what is actually visible. A screenshot alone cannot prove movement or state change;
use a temporal visual episode when motion, pacing, interpolation, or stutter matters, then watch its
rendered review before judging it.

Compare the entire shared heartbeat window across every fingerprint field (currently 25). Do not skip an initial
failure or move the lower bound to make the result green. Diagnostic reports using typed JSON audit
records need the typed comparator; the legacy `compare_determinism_reports.sh` can report "no
fingerprints" for that format, which is unsupported input rather than a pass.

The evidence record must identify the source revision and tree, both build manifests and artifact
hashes, operating systems, transport, host/client roles, scenario and seed/save, the exact input
sequence, shared heartbeat window and duration, desync/crash/lifecycle result, visual judgment,
artifact paths, and any gap. A direct-IP run proves the simulation path it exercised. It does not
prove the Steam lobby, relay or invite path, even if Steam initialized in those players.

On Windows, a player launched over SSH can land in Session 0 and stall during DX11 window setup.
Identify the exact executable, PID, session, and log first. Preserve the failed attempt, then launch
only the task-owned player in the already logged-in desktop session through a uniquely named scoped
task. Remove only that task, its config, and its positively identified player during cleanup. Never
stop Steam, another game, or an unrelated Unity process.

The 2026-09-09 fresh-world Windows-host/macOS-client run is the motivating witness: 57 shared
heartbeats across three recovery epochs differed only in `vision` and the combined fingerprint.
Both peers had 1,678 unkeyed holders; 50 active item-9 holders retained enemy range 175 on the host
and 60 on the restored client. The host and client screenshots were opened and showed the heartbeat-8
vision verdict and failed recovery. The Guardian Swarmer prefab authors enemy range 60, while its config and live spawn use 175
(`AncientGuardianSwarmerEntity.prefab:264`, `AncientGuardianSwarmerConfig.asset:1072`,
`ExecuteShipSpawnCommandSystem.SetupShip`). `ConfigLoadingUtil.InitializeKnnVision` previously
initialized only the fleet range on enemy prefabs, so snapshot reconstruction retained 60.
The fix still requires the full gate above.
