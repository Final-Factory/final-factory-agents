---
name: verify-simulation-at-a-slow-hosts-frame-rate
description: "A simulation, timing or system-placement change is verified at both frame cadences: a frame without a heartbeat must change no simulation state, and the multiplayer check holds the host near one frame per heartbeat against fast clients. A same-speed pair cannot see a frame-order fork."
date: 2026-10-04
---

# Verify simulation at a slow host's frame rate

**Rule.** Simulation runs only on the heartbeat (the `FFFixed*` groups and the ops the ordered drain
applies); everything that runs per rendered frame is presentation and writes nothing the simulation
reads, derived caches included. Every claim that a simulation, timing or system-placement change is
deterministic rests on two checks:

1. a test that runs one rendered frame **without** a heartbeat through the real group placement and
   asserts that no simulation state changed, then one **with** a heartbeat (pattern:
   `Assets/Tests/Multiplayer/PerFrameSimulationWriteTest.cs`);
2. a multiplayer run where the host is held near one frame per heartbeat (about 20 fps at 16 UPS)
   against 60 fps clients, and the reverse.

A pair of peers at the same speed cannot show the fork: it only appears when one peer applies an op
and the next heartbeat in the same frame and the other does not.

**Why.** 2026-10-03 (w342, w356). A Steam Deck host at about 20 fps forked alone a few heartbeats
after an Unbuild (0.50.0.71, session e8242f4c). The deletion chain and the item recount ran every
frame in `FFControllerLateGroup`: on a 60 fps client they ran between the op and the next fixed
step, on the host after it. Every nightly pair ran its peers uncapped on one PC, so no scenario
could see it. The audit that followed found five more per-frame writers of simulation state (heat
production, a ship's `LinearMotion.Disable`, the networked item cache, a star's slots, a component
added to every transform entity), a host-only request leg advancing a saved counter, and a
`DisabledKnnWanderSystem` that threw in the editor and ran in release players. The census counted
77k presentation entities through that every-entity component.

**How to apply.**

- Placing or moving a system: name its group in the PR. A per-frame system must pass
  `PerFrameSystemCensusTest` with a reason, and a `[Save]` write from per-frame code is a move or a
  listed reason, never silent.
- Moving a per-frame writer to the tick: put it OrderLast in its own controller group's fixed
  subgroup, so a heartbeat frame runs it where it ran before.
- Host-only code (a request leg, a publisher) writes no simulation state; the op's apply does, on
  every peer.
- The multiplayer check names its frame rates. Slow host with the nightly harness:
  `ffnightly.py run ... --peer-arg host=-ffFeelProbe --peer-arg host=-ffFeelFps --peer-arg host=20
  --peer-arg host=-ffFeelVsync --peer-arg host=0` (the feel probe holds `Application.targetFrameRate`);
  the reverse puts the same flags on the clients.
- [The merge checklist](../checklists/merge.md) carries the line for `Kind: simulation`.
