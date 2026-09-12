---
name: project-unified-16ups-smooth-presentation
description: "Ben's design goal: one 16 UPS baseline for single-player and multiplayer with smooth per-frame presentation. Feature 057 owns the program; read its plan for where the staged work stands."
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

**Where the program stands is a fact about the repo, not about this file.** Read the dated SESSION
HANDOFF at the top of `specs/057-unified-rate-smooth-presentation/plan.md` and the task states in
that feature's `tasks.md` before planning anything here, and check whether the tip commits are
ancestors of `origin/develop` rather than trusting a "done" line.

Two things that stay true whatever the stage:

- Each stage is presentation-only, proven by an on/off paired-audit bit-identity run. A stage that
  changed a simulation value is not a presentation change however it was framed.
- The single-player 60→16 flip is gated on auditing every heartbeat-count-keyed constant. Do not
  treat the flip as a config edit.

Related: [[player-domain-already-conventional]].
