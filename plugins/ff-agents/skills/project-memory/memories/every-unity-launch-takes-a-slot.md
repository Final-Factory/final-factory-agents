---
name: every-unity-launch-takes-a-slot
description: Every Unity process counts toward a machine's max_unity; launches other than `unity start` wait for a slot (unity-slot run / scripts/unity_slot.py), a peer run asks for all its editors at once
---

# Every Unity launch takes a slot (w469)

**Rule.** A machine's editor limit counts every top-level Unity process there: sandbox editors,
the owner's own, `-batchmode` builds and test runs, peer-run clone editors, editors scripts
start. AssetImportWorkers, bcl.exe and built players are not counted. Interactive editors start
through FF Factory's `unity start`. Every other launch runs under `unity-slot run [--count N] --
<command>` (FF Factory daemon agents) or `python scripts/unity_slot.py run ...` (game repo), which
waits in the machine's queue. A run needing N editors asks for N at once.

**Why.** On 2026-10-05 LothDesktop hit 63 of 64 GB RAM and 100% CPU. It had one interactive
editor and three batch player builds, each with Burst's bcl.exe at 4-10 GB, and its limit of 3
counted only the interactive editor. Lothsahn: "Can we just account for every unity editor process
that's running?"

**How to apply.**
- A refused `unity start` names who holds the slots: wake_me and retry.
- A refused slot request says why, for instance "would wait forever": release what you hold and
  ask for everything at once.
- Never kill another run's Unity to make room.
- Details: FF Factory `docs/unity-lifecycle.md`, "Unity slots"; editor-ops, "Unity slots".
