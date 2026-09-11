---
name: feedback-prove-over-live-networked-machines
description: "Ben (2026-09-11): always test in live networked multiplayer games between machines on his network — a determinism/multiplayer fix is proven by a cross-machine networked leg (BEAST Windows host / Mac peer), never by an editor pair on one box."
---

# Prove multiplayer work over live networked machines (Ben, 2026-09-11)

**What Ben said:** "Remember you need to always be testing in live networked multiplayer games
over machines on my network."

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
