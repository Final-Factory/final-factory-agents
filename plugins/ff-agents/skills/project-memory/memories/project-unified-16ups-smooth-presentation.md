---
name: project-unified-16ups-smooth-presentation
description: "Ben's design goal: one 16 UPS baseline for single-player and multiplayer with smooth per-frame presentation. Feature 057 owns the program. Player, belts, and projectile particles are approved; Phase C world movers and paired determinism proof remain."
metadata:
  node_type: memory
  type: project
  modified: 2026-08-02
---

# Unified 16 UPS with smooth presentation

Ben's design direction is one 16 UPS baseline for both single-player and multiplayer, while
player movement, rendering, UI progress, and every other visible action remain smooth. The player
should never perceive the simulation rate.

Feature `specs/057-unified-rate-smooth-presentation/` is the staged program:

1. Smooth the local player and camera.
2. Smooth world entities, including belts and projectile particles.
3. Smooth UI values that currently step on heartbeats.
4. Flip single-player from 60 UPS to 16 UPS after auditing heartbeat-count-based constants.

The architectural boundary is strict: authoritative simulation stays discrete, deterministic,
and fixed-point; presentation runs every rendered frame and may use floats, but must never feed
values back into simulation (`CLAUDE.md`, "Key Constraints" → "Simulation vs presentation").

Current progress as of 2026-08-02:

- User Story 1, local ship and camera glide, is complete.
- User Story 2 phases A and B are complete. Belt movement was approved. Projectile companion
  particles now follow the interpolated projectile pose and Ben approved the final feel after the
  review-hardening follow-up (`specs/057-unified-rate-smooth-presentation/plan.md`, latest SESSION
  HANDOFF; commits `200c2a414`, `67ca33670`).
- The fast EditMode suite passed after the final follow-up: 2074 total, 2071 passed, 0 failed, and
  3 documented skips (MCP job `69714b72f3eb40e6a97434a984451e44`).
- The formal busy-belt jam-stop checkpoint still needs to be closed unless that behavior was
  explicitly observed during the earlier belt approval
  (`specs/057-unified-rate-smooth-presentation/tasks.md`, T021).
- Phase C world movers, paired on/off determinism proof, UI smoothing, and the single-player rate
  flip remain open (`specs/057-unified-rate-smooth-presentation/tasks.md`, T024–T028; feature
  `spec.md`, User Stories 3–4). Read the latest handoff at the top of the feature plan before
  continuing.

Related: [[player-domain-already-conventional]].
