---
name: feedback-prove-over-live-networked-machines
description: "Ben (2026-09-11): always test in live networked multiplayer games between machines on his network — a determinism/multiplayer fix is proven by a cross-machine networked leg (BEAST Windows host / Mac peer), never by an editor pair on one box."
---

# Prove multiplayer work over live networked machines (Ben, 2026-09-11; reinforced 2026-09-20)

**What Ben said:** "Remember you need to always be testing in live networked multiplayer games
over machines on my network."

## Standing orchestration requirement — 2026-09-20

Ben: “make sure youre testing using all machines on the network, do real tests. make use of the other machines to do parallel tasks too if necessary. you are supposed to be orchestating work using all machines.”

- At the start of an orchestration lane, inventory every reachable machine in the project's
  configured fleet, including additions to the saved routes. Assign each available machine a
  concrete role. Do not quietly reduce the run to the driver's machine or a familiar pair.
  Record an unavailable/busy machine and the actual reason; recover in-scope failures yourself.
- Multiplayer/gameplay acceptance runs the actual scenario in live built players across all
  available fleet machines, with matching source revisions and verified build artifacts. The
  current desktop fleet is M5, M3 and BEAST. Editor probes and unit tests are intermediate
  evidence; they do not replace this run. Host choice follows the scenario, not the historical
  BEAST-host example below. Preserve architecture, platform, roles, PIDs, commands and reports.
- Use spare machines for useful independent work while the critical path runs: platform builds,
  test suites, artifact/save verification, source investigation, or bounded remote workers.
  Prefer a real remote assignment when independent work and capacity exist. Local children all
  run on the driver's host; naming one “M3” does not distribute work. Do not create busywork or
  duplicate the same test merely to occupy a machine.
- Keep a per-machine ownership/status record. One writer/editor/build owner per checkout; use
  isolated checkouts for concurrent edits. Never sync into a checkout with an active editor job.
  Bound remote workers, preserve other work, and collect real exit codes and artifacts.
- The orchestrator owns every dispatched job through completion, failure or a concrete blocker,
  and reports the actual machine coverage with the result. No “tests passed” claim based only
  on launch receipts, command acceptance, an idle world, or one peer's report.
- Apply this automatically. Ben should not need to repeat the multi-machine requirement.
  An explicit narrower task or constraint from Ben can override it; explain any remaining gap.

## Coordinator sequencing and worker artifacts

- Finish the host's entire pre-connect chain before launching any client. `host-ready` is
  emitted before that chain, and `pre-connect-command-complete` also appears after each
  individual segment. Require the completed **full chain**, followed by
  `waiting-host-peers-connected`, before joining. Feature074 t34 connected during the final
  five-second wait; `enemy.activateeconomy` correctly rejected the now-postjoin mutation and
  invalidated the setup. Source: `LocalMultiplayerAutomationBootstrap.RunHostAsync` and
  `ExecuteChainedCommandsAsync`; `LocalMultiplayerAutomationCommandRunner.EnsureHostBeforeClientsJoin`.
- A remote worker's artifact and the CLI final-response output must have different paths.
  For example, ask it to write `recipe.md` and use `codex exec -o result.txt`. In feature074's
  t33 M3 job, using `final.txt` for both overwrote the completed recipe with the final
  acknowledgment. Retrieve and inspect the actual artifacts, not just the worker's final text.

Read [fleet operations](../../editor-ops/references/codex-fleet.md) for routes, remote workers,
capacity and editor ownership. These obligations apply to both Claude Code and Codex; use each
runtime's own worker mechanisms.

**Why:** an editor pair on one machine shares the platform, the codegen, the frame cadence and
the file system, so it cannot see the cross-platform and cross-machine classes that players hit
(float ULP noise between x64 and arm64, join/rejoin over a real transport, a built player's
Burst/IL2CPP code paths). The same day's B3 fix (`EntityGridPersistenceSystem`) was first
"proven" as an M5 editor pair (rejoin11) and had to be re-proven cross-machine before it counted.

**How to apply:**
- Put the cross-machine leg in the plan BEFORE claiming "proven"; unit tests, EditMode suites and
  editor-pair legs are supporting evidence only (see
  [[cross-machine-built-player-gameplay-acceptance]] for the full gate).
- Host on BEAST with a built player: stage the build with the tar.gz + scp + `make_manifest.py`
  recipe and launch through `run_saved_cross_platform_peer.py` (the `_outlive` variant adds
  `--outlive-pair-break` → `-ffAutomationOutlivePairBreak true` for park + reclaim rejoin legs);
  the peer is a built Mac player (M5/M3) or, when no Mac rebuild is needed, the M5 editor with a
  `.ff-local-automation.json` pointing at the remote `Host`/`Port` (Tailscale `100.86.157.116:7827`
  worked; the LAN `10.0.0.x` addresses also do). See
  [[cross-platform-leg-staging-and-the-movers-position-residual]] for the exact commands.
- A rejoin over the network: client `PostReadyCommand` with
  `ffauto:net.rejoin|<host>|<port>|50|realmap`; the host must outlive the pair break.
- Proof rejoin12-44a7f32ff (BEAST built host / M5 editor client): `GridRestore` derived
  229,109→restored 230,625 and 229,110→230,626 after the rejoin, `mapEntries` identical on both
  peers for 1000+ hb, only `movers` differed (the known cross-platform position-flip residual).
- Report what the leg could NOT prove (a direct-IP run says nothing about the Steam lobby/relay
  path; an editor client says nothing about the built Mac player).
